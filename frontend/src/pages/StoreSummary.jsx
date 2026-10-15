import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Store, TrendingUp } from 'lucide-react';

export default function StoreSummary() {
  const { id } = useParams();
  const [campaign, setCampaign] = useState(null);
  const [storeKPIs, setStoreKPIs] = useState([]);

  useEffect(() => {
    // 1. Get Campaign Info
    axios.get(`http://localhost:8000/api/campaigns/${id}`)
      .then(res => {
        setCampaign(res.data);
        // 2. Get Stores comparison
        return axios.get(`http://localhost:8000/api/analytics/${id}/comparison`);
      })
      .then(res => setStoreKPIs(res.data))
      .catch(console.error);
  }, [id]);

  if (!campaign) return <div className="text-white">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <div>
        <Link to={`/campaign/${encodeURIComponent(campaign.campaign_type)}`} className="text-sm text-primary hover:underline mb-2 inline-block">← Back to Campaigns</Link>
        <h1 className="text-3xl font-bold text-white tracking-tight">{campaign.campaign_name} - Stores</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {storeKPIs.map(store => (
          <Link 
            key={store.store_name}
            to={`/campaign/id/${id}/store/${encodeURIComponent(store.store_name)}`}
            className="bg-darkCard border border-slate-700 rounded-2xl p-6 hover:border-emerald-500 transition group block relative overflow-hidden"
          >
            <div className="absolute right-0 top-0 w-24 h-24 bg-gradient-to-br from-emerald-500/10 to-transparent rounded-bl-full pointer-events-none"></div>
            
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                <Store size={20} />
              </div>
              <h3 className="text-xl font-semibold">{store.store_name}</h3>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-1">Purchases</p>
                <p className="text-xl text-white">{store.purchase_count}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-1">ROI</p>
                <p className={`text-xl flex items-center gap-1 ${store.roi > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {store.roi > 0 && <TrendingUp size={16} />}
                  {store.roi.toFixed(1)}%
                </p>
              </div>
            </div>
            
            <div className="mt-4 pt-4 border-t border-slate-700/50">
              <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-1">Total Sales</p>
              <p className="text-lg font-medium text-slate-200">₹{store.purchase_value.toLocaleString()}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
