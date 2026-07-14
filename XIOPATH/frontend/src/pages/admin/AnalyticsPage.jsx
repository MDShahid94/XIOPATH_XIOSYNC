/**
 * XIOPATH — Analytics Page (Admin)
 * ===================================
 * System metrics visualization with Recharts.
 * Execution trends, success rates, and performance data.
 */
import React, { useState, useEffect } from 'react';
import {
  BarChart3, RefreshCw, TrendingUp, Clock, CheckCircle,
  XCircle, Activity, Calendar
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

// Custom tooltip matching XIOPATH design
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--xp-bg-elevated)', border: '1px solid var(--xp-border-default)',
      borderRadius: 'var(--xp-radius-md)', padding: '8px 12px',
      boxShadow: 'var(--xp-shadow-lg)',
    }}>
      <div style={{ fontSize: '11px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ fontSize: '12px', color: p.color, fontFamily: 'var(--xp-font-mono)' }}>
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
};

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('7d');

  // Generate realistic mock data
  const executionData = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(Date.now() - (6 - i) * 86400000);
    return {
      date: d.toLocaleDateString('en-US', { weekday: 'short' }),
      successful: Math.floor(Math.random() * 30 + 15),
      failed: Math.floor(Math.random() * 8 + 1),
    };
  });

  const performanceData = Array.from({ length: 24 }, (_, i) => ({
    hour: `${i}:00`,
    latency: Math.floor(Math.random() * 500 + 200),
    throughput: Math.floor(Math.random() * 15 + 3),
  }));

  const tierData = [
    { name: 'Server Primary', value: 45, color: '#06D6A0' },
    { name: 'Server Secondary', value: 128, color: '#00E5FF' },
    { name: 'Local Primary', value: 312, color: '#B388FF' },
    { name: 'Local Secondary', value: 567, color: '#666' },
  ];

  const stats = {
    total: executionData.reduce((sum, d) => sum + d.successful + d.failed, 0),
    successRate: Math.round(
      executionData.reduce((sum, d) => sum + d.successful, 0) /
      executionData.reduce((sum, d) => sum + d.successful + d.failed, 0) * 100
    ),
    avgLatency: Math.round(performanceData.reduce((s, d) => s + d.latency, 0) / performanceData.length),
    peakHour: performanceData.reduce((max, d) => d.throughput > max.throughput ? d : max).hour,
  };

  useEffect(() => { setTimeout(() => setLoading(false), 500); }, []);

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Analytics</h1>
          <p className="xp-page-subtitle">System performance metrics and execution trends</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--xp-space-2)' }}>
          <div className="xp-tabs" style={{ marginBottom: 0 }}>
            {['24h', '7d', '30d'].map((r) => (
              <button key={r} className={`xp-tab ${timeRange === r ? 'xp-tab-active' : ''}`}
                onClick={() => setTimeRange(r)}>
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Stats ────────────────────────────────── */}
      <div className="xp-grid xp-grid-4" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {[
          { label: 'Total Executions', value: stats.total, icon: Activity, color: 'var(--xp-cyan)' },
          { label: 'Success Rate', value: `${stats.successRate}%`, icon: CheckCircle, color: 'var(--xp-success)' },
          { label: 'Avg. Latency', value: `${stats.avgLatency}ms`, icon: Clock, color: 'var(--xp-purple)' },
          { label: 'Peak Hour', value: stats.peakHour, icon: TrendingUp, color: 'var(--xp-warning)' },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="xp-card" style={{ position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: '-20px', right: '-20px', width: '80px', height: '80px', borderRadius: '50%', background: `radial-gradient(circle, ${s.color}15, transparent 70%)`, pointerEvents: 'none' }} />
              <div className="xp-stat">
                <span className="xp-stat-label">{s.label}</span>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className="xp-stat-value">{loading ? '—' : s.value}</span>
                  <Icon size={20} style={{ color: s.color }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="xp-grid xp-grid-2" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {/* ─── Execution Trend ────────────────────── */}
        <div className="xp-card">
          <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)' }}>
            Execution Trend
          </h3>
          <div style={{ width: '100%', height: '250px' }}>
            <ResponsiveContainer>
              <BarChart data={executionData} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: '#999', fontSize: 11 }} />
                <YAxis tick={{ fill: '#999', fontSize: 11 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="successful" stackId="a" fill="#06D6A0" radius={[0, 0, 0, 0]} name="Successful" />
                <Bar dataKey="failed" stackId="a" fill="#EF4444" radius={[4, 4, 0, 0]} name="Failed" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ─── Memory Tier Distribution ───────────── */}
        <div className="xp-card">
          <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)' }}>
            Memory Tier Distribution
          </h3>
          <div style={{ width: '100%', height: '250px' }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={tierData}
                  cx="50%" cy="50%" outerRadius={90} innerRadius={55}
                  paddingAngle={3} dataKey="value"
                  stroke="none"
                >
                  {tierData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  verticalAlign="bottom"
                  formatter={(value) => <span style={{ color: '#999', fontSize: '11px' }}>{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ─── Performance Over Time ────────────────── */}
      <div className="xp-card">
        <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)' }}>
          Performance (24h)
        </h3>
        <div style={{ width: '100%', height: '250px' }}>
          <ResponsiveContainer>
            <AreaChart data={performanceData}>
              <defs>
                <linearGradient id="gradLatency" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00E5FF" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00E5FF" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="hour" tick={{ fill: '#999', fontSize: 10 }} interval={3} />
              <YAxis tick={{ fill: '#999', fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="latency" stroke="#00E5FF" fill="url(#gradLatency)" strokeWidth={2} name="Latency (ms)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
