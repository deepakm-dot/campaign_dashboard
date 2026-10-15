import { useState } from 'react';
import axios from 'axios';
import { UploadCloud, CheckCircle2, AlertCircle } from 'lucide-react';

export default function DataUpload() {
  const [status, setStatus] = useState({ type: '', msg: '' });

  const handleUpload = async (e, endpoint) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    
    // For campaign customers we need a campaign ID, let's assume it's passed or selected. 
    // In a real app, you'd have a dropdown to select campaign first.
    // For now we'll just show the upload UI for master and billing.
    
    setStatus({ type: 'loading', msg: 'Uploading...' });
    try {
      const res = await axios.post(`http://localhost:8000/api/upload/${endpoint}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setStatus({ type: 'success', msg: res.data.message });
    } catch (err) {
      setStatus({ type: 'error', msg: err.response?.data?.detail || err.message });
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Data Integration</h1>
        <p className="text-slate-400 mt-2">Upload Excel/CSV files to update dashboard data in PostgreSQL.</p>
      </div>

      {status.msg && (
        <div className={`p-4 rounded-xl flex items-center gap-3 ${
          status.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 
          status.type === 'loading' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
          'bg-red-500/10 text-red-400 border border-red-500/20'
        }`}>
          {status.type === 'success' ? <CheckCircle2 /> : <AlertCircle />}
          {status.msg}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700">
          <h3 className="text-lg font-medium mb-4">1. Campaign Master Data</h3>
          <p className="text-sm text-slate-400 mb-6">Upload campaigns list, costs, and dates.</p>
          <label className="flex items-center justify-center gap-2 w-full py-3 px-4 bg-primary text-white rounded-xl cursor-pointer hover:bg-blue-600 transition">
            <UploadCloud size={20} />
            <span>Select File</span>
            <input type="file" className="hidden" accept=".csv,.xlsx" onChange={(e) => handleUpload(e, 'campaign-master/')} />
          </label>
        </div>

        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700">
          <h3 className="text-lg font-medium mb-4">2. Billing Data</h3>
          <p className="text-sm text-slate-400 mb-6">Upload daily sales invoices and products.</p>
          <label className="flex items-center justify-center gap-2 w-full py-3 px-4 bg-slate-700 text-white rounded-xl cursor-pointer hover:bg-slate-600 transition">
            <UploadCloud size={20} />
            <span>Select File</span>
            <input type="file" className="hidden" accept=".csv,.xlsx" onChange={(e) => handleUpload(e, 'billing-data/')} />
          </label>
        </div>
      </div>
      
      {/* Note: Campaign Customers Upload requires selecting a campaign first, UI omitted for brevity but API is ready */}
    </div>
  );
}
