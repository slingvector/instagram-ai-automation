'use client';
import { useEffect, useState, useRef } from 'react';
import { Terminal, Database, RotateCw, Activity, Server, Smartphone, Trash2, ShieldAlert } from 'lucide-react';

export default function MonitoringPage() {
  const [activeJobs, setActiveJobs] = useState([]);
  const [failedJobs, setFailedJobs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [health, setHealth] = useState({ adb: 'error', firebase: 'error', manifest: 'error' });
  const [loading, setLoading] = useState(true);
  const logEndRef = useRef(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch('/api/monitoring');
        const data = await res.json();
        setActiveJobs(data.active || []);
        setFailedJobs(data.failed || []);
        
        const logRes = await fetch('/api/logs');
        const logData = await logRes.json();
        setLogs(logData.logs || []);

        const healthRes = await fetch('/api/health');
        const healthData = await healthRes.json();
        setHealth(healthData);

      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleAction = async (action) => {
    if (action === 'purge_db' && !window.confirm('Are you ABSOLUTELY sure? This will wipe the ENTIRE discovery database and all pipeline states. The scraper will start completely from scratch.')) {
      return;
    }
    
    try {
      const res = await fetch('/api/manage-db', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      alert(data.message);
    } catch (e) {
      alert('Action failed.');
    }
  };

  const StatusDot = ({ status }) => {
    const color = status === 'online' ? 'var(--success)' : status === 'offline' ? 'var(--danger)' : 'var(--warning)';
    return <span style={{ display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', background: color, boxShadow: `0 0 10px ${color}` }}></span>;
  };

  const getLogClass = (line) => {
    if (line.includes('[ERROR]') || line.includes('FATAL')) return 'error';
    if (line.includes('[WARNING]')) return 'warning';
    return 'info';
  };

  if (loading) return <div><h2>Loading Monitoring Data...</h2></div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <h1>Pipeline Observatory</h1>
        <div style={{ display: 'flex', gap: '16px' }}>
          <div className="glass-panel" style={{ padding: '12px 24px', display: 'flex', gap: '24px', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}><StatusDot status={health.adb} /> <Smartphone size={16}/> LocalSend / ADB</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}><StatusDot status={health.firebase} /> <Database size={16}/> Firebase ADC</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}><StatusDot status={health.manifest} /> <Server size={16}/> Config Engine</div>
          </div>
        </div>
      </div>
      
      {/* Database Management Controls */}
      <div className="glass-panel" style={{ marginBottom: '40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(59, 130, 246, 0.05)', borderColor: 'var(--accent-glow)' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px', fontSize: '1.2rem' }}><Database size={20} color="var(--accent-color)" /> Database Integrity Manager</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: 0 }}>Force state transitions or hard-reset the pipeline discovery engine directly from the UI.</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button className="btn" onClick={() => handleAction('retry_failed')}><RotateCw size={16} /> Retry All Failed Jobs ({failedJobs.length})</button>
          <button className="btn btn-danger" onClick={() => handleAction('purge_db')}><Trash2 size={16} /> Purge Dedup & State DB</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginBottom: '40px' }}>
        
        {/* Active Jobs */}
        <div className="glass-panel">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}><Activity size={20} color="var(--success)"/> Active Jobs ({activeJobs.length})</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '500px', overflowY: 'auto', paddingRight: '12px' }}>
            {activeJobs.map(job => (
              <div key={job.url} style={{ padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', borderLeft: '4px solid var(--accent-color)' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '1px' }}>{job.source} | {job.platform}</div>
                <div style={{ fontWeight: '500', marginBottom: '12px', wordBreak: 'break-all', fontSize: '0.9rem' }}>{job.url}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.7rem', background: 'var(--accent-glow)', color: '#fff', padding: '4px 10px', borderRadius: '12px', fontWeight: 'bold', letterSpacing: '0.5px' }}>
                    {job.state.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Last Update: {new Date(job.updated_at).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
            {activeJobs.length === 0 && <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '40px 0' }}>No active jobs in the queue.</div>}
          </div>
        </div>

        {/* Failed Jobs */}
        <div className="glass-panel">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}><ShieldAlert size={20} color="var(--danger)"/> Failed Jobs ({failedJobs.length})</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '500px', overflowY: 'auto', paddingRight: '12px' }}>
            {failedJobs.map(job => {
              let meta = {};
              try { meta = JSON.parse(job.ai_metadata || '{}'); } catch(e) {}
              return (
                <div key={job.url} style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '12px', borderLeft: '4px solid var(--danger)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>{job.source}</div>
                  <div style={{ fontWeight: '500', marginBottom: '12px', wordBreak: 'break-all', fontSize: '0.9rem' }}>{job.url}</div>
                  <div style={{ fontSize: '0.8rem', color: '#ffaaaa', background: 'rgba(0,0,0,0.4)', padding: '12px', borderRadius: '8px', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {job.error_message || meta.error_message || meta.error || 'Unknown Error'}
                  </div>
                </div>
              );
            })}
            {failedJobs.length === 0 && <div style={{ color: 'var(--success)', textAlign: 'center', padding: '40px 0' }}>Zero failed jobs! The pipeline is humming perfectly.</div>}
          </div>
        </div>

      </div>

      {/* Live Log Streamer */}
      <div className="glass-panel">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}><Terminal size={20} color="var(--accent-color)"/> Live Industrial Logs (Tail)</h2>
        <div className="terminal-window">
          {logs.map((line, i) => (
            <div key={i} className={`terminal-line ${getLogClass(line)}`}>{line}</div>
          ))}
          {logs.length === 0 && <div style={{ color: '#666' }}>Waiting for log data...</div>}
          <div ref={logEndRef} />
        </div>
      </div>

    </div>
  );
}
