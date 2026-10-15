import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';

export default function StoreDetail() {
  const { id, store_name } = useParams();
  const [kpi, setKpi] = useState(null);
  const [products, setProducts] = useState([]);
  const [trend, setTrend] = useState([]);
  
  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#64748b'];

  useEffect(() => {
    // Fetch KPI
    axios.get(`http://localhost:8000/api/analytics/${id}/store/${store_name}/kpi`)
      .then(res => setKpi(res.data));
    
    // Fetch Products
    axios.get(`http://localhost:8000/api/analytics/${id}/store/${store_name}/products`)
      .then(res => setProducts(res.data));
      
    // Fetch Trend
    axios.get(`http://localhost:8000/api/analytics/${id}/store/${store_name}/trend`)
      .then(res => setTrend(res.data));
  }, [id, store_name]);

  if (!kpi) return <div>Loading...</div>;

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <div>
        <Link to={`/campaign/id/${id}`} className="text-sm text-primary hover:underline mb-2 inline-block">← Back to Store List</Link>
        <h1 className="text-3xl font-bold text-white tracking-tight">{store_name} Analysis</h1>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700">
          <p className="text-sm text-slate-400 font-medium mb-1">Purchase Count</p>
          <p className="text-3xl font-bold text-white">{kpi.purchase_count}</p>
        </div>
        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700">
          <p className="text-sm text-slate-400 font-medium mb-1">Purchase Value</p>
          <p className="text-3xl font-bold text-emerald-400">₹{kpi.purchase_value.toLocaleString()}</p>
        </div>
        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700">
          <p className="text-sm text-slate-400 font-medium mb-1">ROI</p>
          <p className={`text-3xl font-bold ${kpi.roi >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {kpi.roi.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Trend Chart */}
        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700 h-[400px]">
          <h3 className="text-lg font-semibold mb-6">Daily Sales Trend</h3>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#94a3b8" />
              <YAxis yAxisId="left" stroke="#3b82f6" />
              <YAxis yAxisId="right" orientation="right" stroke="#10b981" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }} />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="sales_value" stroke="#3b82f6" name="Sales (₹)" strokeWidth={3} />
              <Line yAxisId="right" type="monotone" dataKey="qty_sold" stroke="#10b981" name="Quantity" strokeWidth={3} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Pie Chart */}
        <div className="bg-darkCard p-6 rounded-2xl border border-slate-700 h-[400px]">
          <h3 className="text-lg font-semibold mb-6">Revenue Distribution</h3>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={products}
                cx="50%"
                cy="50%"
                innerRadius={80}
                outerRadius={120}
                paddingAngle={5}
                dataKey="sales_value"
                nameKey="category"
              >
                {products.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `₹${value.toLocaleString()}`} contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
      
      {/* Product Table */}
      <div className="bg-darkCard p-6 rounded-2xl border border-slate-700 overflow-hidden">
        <h3 className="text-lg font-semibold mb-6">Product Performance (All Customers)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="py-4 px-4 text-slate-400 font-medium">Category</th>
                <th className="py-4 px-4 text-slate-400 font-medium">Qty Sold</th>
                <th className="py-4 px-4 text-slate-400 font-medium">Sales Value (₹)</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p, i) => (
                <tr key={i} className="border-b border-slate-800 hover:bg-slate-800/50">
                  <td className="py-4 px-4">{p.category}</td>
                  <td className="py-4 px-4">{p.qty_sold}</td>
                  <td className="py-4 px-4">₹{p.sales_value.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
    </div>
  );
}
