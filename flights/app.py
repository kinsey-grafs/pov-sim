import logging
import time
from functools import wraps

from flasgger import Swagger
from flask import Flask, jsonify, request
from flask_cors import CORS
from utils import get_random_int

# metrics imports
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.metrics import set_meter_provider, get_meter

# traces imports
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# log imports
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

# ----------------------------
# Setup metrics, logging, and tracing
# ----------------------------

resource = Resource(attributes={
    SERVICE_NAME: "flights"
})

collector_endpoint = "http://alloy:4317"


meter = get_meter("flights")

metrics.set_meter_provider(
    MeterProvider(
        resource=resource,
        metric_readers=[(PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=collector_endpoint)
        ))],
    )
)

# create meter helper function for custom metrics
def track_endpoint_metrics(endpoint_name):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            start = time.time()
            method = request.method
            try:
                response = f(*args, **kwargs)
                status = response[1] if isinstance(response, tuple) else 200
            except Exception as e:
                status = 500
                raise e
            finally:
                duration_ms = (time.time() - start) * 1000
                endpoint_counter.add(1, attributes={
                    "endpoint": endpoint_name,
                    "method": method,
                    "status_code": str(status)
                })
                endpoint_duration.record(duration_ms, attributes={
                    "endpoint": endpoint_name,
                    "method": method,
                    "status_code": str(status)
                })
            return response
        return wrapped
    return decorator

# Custom metric - flight_bookings_total - A counter to track bookings
flight_booking_counter = meter.create_counter(
    name="flight_bookings_total",
    unit="1",
    description="Total number of flights booked",
)

# Custom metric - flight_booking_duration_ms -A histogram to track booking durations (optional)
flight_booking_duration = meter.create_histogram(
    name="flight_booking_duration_ms",
    unit="ms",
    description="Duration of flight booking processing",
)

# custom metric - A counter for requests per endpoint
endpoint_counter = meter.create_counter(
    name="http_requests_total",
    unit="1",
    description="Total HTTP requests received by endpoint"
)

#custom metric - A histogram for request duration per endpoint
endpoint_duration = meter.create_histogram(
    name="http_request_duration_ms",
    unit="ms",
    description="HTTP request duration in milliseconds"
)

# custom metric - Counter: how many times flights were fetched per airline
flight_fetch_counter = meter.create_counter(
    name="flight_fetch_total",
    unit="1",
    description="Total number of times flight data was fetched"
)

# custom metric - Histogram: how long the flight fetch takes
flight_fetch_duration = meter.create_histogram(
    name="flight_fetch_duration_ms",
    unit="ms",
    description="Duration of flight data fetch in milliseconds"
)

# Tracing
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer_provider = trace.get_tracer_provider()
otlp_trace_exporter = OTLPSpanExporter(endpoint=collector_endpoint, insecure=True)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

# Logging
log_exporter = OTLPLogExporter(endpoint=collector_endpoint, insecure=True)
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

set_logger_provider(logger_provider)

# Connect OpenTelemetry logging to Python logging
otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
otel_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(otel_handler)

# Optional: print to console too
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)



# ----------------------------
# Flask App
# ----------------------------

app = Flask(__name__)
Swagger(app)
CORS(app)

FlaskInstrumentor().instrument_app(app)

@app.route('/health', methods=['GET'])
@track_endpoint_metrics("health")
def health():
    logger.info("Health check called")
    return jsonify({"status": "healthy"}), 200

@app.route("/", methods=['GET'])
@track_endpoint_metrics("home")
def home():
    logger.info("Root endpoint called")
    return jsonify({"message": "ok"}), 200

@app.route("/flights/<airline>", methods=["GET"])
@track_endpoint_metrics("get_flights")
def get_flights(airline):
    start = time.time()
    try:
        status_code = request.args.get("raise")
        if status_code:
            logger.error(f"Triggering error with code: {status_code}")
            raise Exception(f"Encountered {status_code} error")  # Simulate error
        random_int = get_random_int(100, 999)
        logger.info(f"Fetched flight data for airline {airline}")

        # Record successful fetch
        flight_fetch_counter.add(1, attributes={"airline": airline, "status": "200"})
        return jsonify({airline: [random_int]}), 200

    except Exception as e:
        # Count errors too (e.g. simulated failures)
        flight_fetch_counter.add(1, attributes={"airline": airline, "status": "500"})
        raise e

    finally:
        duration_ms = (time.time() - start) * 1000
        flight_fetch_duration.record(duration_ms, attributes={"airline": airline})

@app.route("/flight", methods=["POST"])
@track_endpoint_metrics("book_flight")
def book_flight():
    start = time.time()
    logger.info("Booking flight called")
    status_code = request.args.get("raise")
    if status_code:
        logger.error(f"Booking error triggered: {status_code}")
        raise Exception(f"Encountered {status_code} error")

    passenger_name = request.args.get("passenger_name")
    flight_num = request.args.get("flight_num")
    booking_id = get_random_int(100, 999)

    # Record custom metrics
    flight_booking_counter.add(1, attributes={"airline": flight_num})
    duration_ms = (time.time() - start) * 1000
    flight_booking_duration.record(duration_ms, attributes={"airline": flight_num})

    logger.info(f"Booked flight {flight_num} for {passenger_name} with ID {booking_id}")
    return jsonify({
        "passenger_name": passenger_name,
        "flight_num": flight_num,
        "booking_id": booking_id
    }), 200

if __name__ == "__main__":
    app.run(debug=True, port=5001)
