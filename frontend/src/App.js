import './App.css';
import Home from './pages/Home';
import Airlines from './pages/Airlines';
import Flights from './pages/Flights';
import Navigation from './components/Navigation';

import {
  createBrowserRouter,
  RouterProvider,
  Outlet,
  matchRoutes,
} from 'react-router-dom';

import {
  initializeFaro,
  createReactRouterV6DataOptions,
  ReactIntegration,
  getWebInstrumentations,
  withFaroRouterInstrumentation,
} from '@grafana/faro-react';

import { TracingInstrumentation } from '@grafana/faro-web-tracing';

// Faro initialization
initializeFaro({
  url: 'https://faro-collector-prod-us-west-0.grafana.net/collect/b97d5c9d810710c7f3c61eb3ec6eb443',
  app: {
    name: 'POV-sim',
    version: '1.0.0',
    environment: 'production',
  },
  instrumentations: [
    ...getWebInstrumentations(),
    new TracingInstrumentation(),
    new ReactIntegration({
      router: createReactRouterV6DataOptions({ matchRoutes }),
    }),
  ],
});

// Layout component with shared UI
const Layout = () => (
  <div className="App">
    <header className="App-header">
      <Navigation />
      <Outlet /> {/* This renders the matched child route */}
    </header>
  </div>
);

// Define routes with layout
const routes = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'flights', element: <Flights /> },
      { path: 'airlines', element: <Airlines /> },
    ],
  },
];

// Instrumented router
const instrumentedRouter = withFaroRouterInstrumentation(
  createBrowserRouter(routes)
);

function App() {
  return <RouterProvider router={instrumentedRouter} />;
}

export default App;
