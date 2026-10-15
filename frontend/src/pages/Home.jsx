import { Link } from 'react-router-dom';
import { Megaphone, Store, Plus } from 'lucide-react';

export default function Home() {
  const categories = [
    { name: 'Marketing Campaign', type: 'Marketing Campaign', icon: <Megaphone className="w-8 h-8 text-blue-400" /> },
    { name: 'Store Inauguration', type: 'Store Inauguration', icon: <Store className="w-8 h-8 text-emerald-400" /> },
    { name: 'Other Campaigns', type: 'Other', icon: <Plus className="w-8 h-8 text-purple-400" /> },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Campaign Categories</h1>
        <p className="text-slate-400 mt-2">Select a campaign type to view performance metrics.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {categories.map((cat) => (
          <Link 
            key={cat.type}
            to={`/campaign/${encodeURIComponent(cat.type)}`}
            className="group relative bg-darkCard border border-slate-700/50 rounded-2xl p-6 hover:bg-slate-800/50 hover:border-slate-600 transition-all overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-white/5 to-transparent rounded-bl-full -mr-8 -mt-8 pointer-events-none group-hover:scale-110 transition-transform"></div>
            
            <div className="bg-slate-900/50 w-16 h-16 rounded-xl flex items-center justify-center mb-6 shadow-inner border border-slate-800">
              {cat.icon}
            </div>
            <h3 className="text-xl font-semibold text-slate-100">{cat.name}</h3>
            <p className="text-sm text-slate-400 mt-2">View and analyze all campaigns under this category.</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
