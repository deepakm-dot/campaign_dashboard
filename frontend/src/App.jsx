import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Home from './pages/Home';
import CampaignListing from './pages/CampaignListing';
import StoreSummary from './pages/StoreSummary';
import StoreDetail from './pages/StoreDetail';
import DataUpload from './pages/DataUpload';
import { LayoutDashboard, UploadCloud } from 'lucide-react';

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-darkBg text-slate-100">
        {/* Sidebar */}
        <aside className="w-64 bg-darkCard border-r border-slate-700 flex flex-col">
          <div className="p-6">
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <LayoutDashboard className="text-primary" />
              Campaign OS
            </h1>
          </div>
          <nav className="flex-1 px-4 space-y-2">
            <Link to="/" className="flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-800 text-white hover:bg-slate-700 transition">
              <LayoutDashboard size={20} />
              Dashboard
            </Link>
            <Link to="/upload" className="flex items-center gap-3 px-4 py-3 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition">
              <UploadCloud size={20} />
              Data Upload
            </Link>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <header className="h-16 bg-darkCard border-b border-slate-700 flex items-center px-8">
            <h2 className="text-lg font-medium">Retail Sales Performance</h2>
          </header>
          
          <div className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/campaign/:type" element={<CampaignListing />} />
              <Route path="/campaign/id/:id" element={<StoreSummary />} />
              <Route path="/campaign/id/:id/store/:store_name" element={<StoreDetail />} />
              <Route path="/upload" element={<DataUpload />} />
            </Routes>
          </div>
        </main>
      </div>
    </Router>
  );
}

export default App;
