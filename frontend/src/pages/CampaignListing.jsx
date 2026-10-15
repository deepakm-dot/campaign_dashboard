import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Calendar, IndianRupee, Users } from 'lucide-react';

export default function CampaignListing() {
  const { type } = useParams();
  const [campaigns, setCampaigns] = useState([]);

  useEffect(() => {
    axios.get(`http://localhost:8000/api/campaigns/category/${type}`)
      .then(res => setCampaigns(res.data))
      .catch(console.error);
  }, [type]);

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <div>
        <Link to="/" className="text-sm text-primary hover:underline mb-2 inline-block">← Back to Categories</Link>
        <h1 className="text-3xl font-bold text-white tracking-tight">{type}</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {campaigns.map(camp => (
          <Link 
            key={camp.id} 
            to={`/campaign/id/${camp.id}`}
            className="bg-darkCard border border-slate-700 rounded-2xl p-6 hover:border-primary transition group"
          >
            <h3 className="text-xl font-semibold mb-4 group-hover:text-primary transition">{camp.campaign_name}</h3>
            
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm text-slate-300">
                <Calendar className="text-slate-500 w-4 h-4" />
                <span>{camp.start_date} to {camp.end_date}</span>
              </div>
              <div className="flex items-center gap-3 text-sm text-slate-300">
                <IndianRupee className="text-emerald-500 w-4 h-4" />
                <span>Cost: ₹{camp.campaign_cost.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-3 text-sm text-slate-300">
                <Users className="text-blue-500 w-4 h-4" />
                <span>Stores: {camp.stores.length}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
