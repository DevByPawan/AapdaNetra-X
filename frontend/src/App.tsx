import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './components/layout/Sidebar';
import { Toast } from './components/common/Feedback';
import { CommandCenter } from './pages/CommandCenter';
import { LiveMap, Forecast, Evacuation, Resources, Simulation, Analytics } from './pages/StubPages';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div
          className="flex min-h-screen"
          style={{ gridTemplateColumns: '220px 1fr' }}
        >
          {/* Sidebar */}
          <Sidebar />

          {/* Page content */}
          <div className="flex-1 min-w-0 overflow-auto">
            <Routes>
              <Route path="/"            element={<CommandCenter />} />
              <Route path="/map"         element={<LiveMap />} />
              <Route path="/forecast"    element={<Forecast />} />
              <Route path="/evacuation"  element={<Evacuation />} />
              <Route path="/resources"   element={<Resources />} />
              <Route path="/simulation"  element={<Simulation />} />
              <Route path="/analytics"   element={<Analytics />} />
            </Routes>
          </div>
        </div>

        {/* Global toast */}
        <Toast />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
