'use client';
import { useEffect, useState } from 'react';

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [reels, setReels] = useState([]);
  const [finishedReels, setFinishedReels] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const metricsRes = await fetch('/api/metrics');
        const metricsData = await metricsRes.json();
        setMetrics(metricsData);

        const reelsRes = await fetch('/api/reels?state=CAPTIONED');
        const reelsData = await reelsRes.json();
        setReels(reelsData.reels || []);

        const finishedRes = await fetch('/api/reels?state=FINISHED&limit=12');
        const finishedData = await finishedRes.json();
        setFinishedReels(finishedData.reels || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    
    // Refresh every 10 seconds
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (url) => {
    await fetch('/api/reels', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, state: 'JOB_CREATED' })
    });
    setReels(reels.filter(r => r.url !== url));
  };

  const handleReject = async (url) => {
    await fetch('/api/reels', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, state: 'FAILED' })
    });
    setReels(reels.filter(r => r.url !== url));
  };

  if (loading) {
    return <div className="layout"><h2>Loading Dashboard...</h2></div>;
  }

  return (
    <div className="layout">
      <h1>AI Ingestion Pipeline</h1>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', marginBottom: '40px' }}>
        <div className="glass-panel metric-card">
          <div className="metric-value">{metrics?.TOTAL || 0}</div>
          <div className="metric-label">Total Scanned</div>
        </div>
        <div className="glass-panel metric-card">
          <div className="metric-value" style={{ color: 'var(--accent-color)' }}>{metrics?.DOWNLOADED || 0}</div>
          <div className="metric-label">Downloaded</div>
        </div>
        <div className="glass-panel metric-card">
          <div className="metric-value" style={{ color: 'var(--warning)' }}>{metrics?.CAPTIONED || 0}</div>
          <div className="metric-label">Awaiting Review</div>
        </div>
        <div className="glass-panel metric-card">
          <div className="metric-value" style={{ color: 'var(--success)' }}>{metrics?.MEDIA_PROCESSED || 0}</div>
          <div className="metric-label">Media Processed</div>
        </div>
      </div>

      <h2>Media Review Queue ({reels.length})</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {reels.map((reel) => {
          let metadata = {};
          try {
            metadata = JSON.parse(reel.ai_metadata || '{}');
          } catch(e) {}
          
          return (
            <div key={reel.url} className="glass-panel" style={{ display: 'flex', gap: '24px' }}>
              <div style={{ flex: '0 0 300px' }}>
                <video 
                  src={reel.gcs_uri ? `/api/video?gcs_uri=${encodeURIComponent(reel.gcs_uri)}` : ''} 
                  controls 
                  style={{ width: '100%', borderRadius: '8px', background: '#000' }} 
                  preload="none"
                />
                <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {reel.url}
                </div>
              </div>
              <div style={{ flex: '1', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-secondary)' }}>Caption</label>
                  <textarea rows="4" defaultValue={metadata.caption || ''} />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-secondary)' }}>Hashtags</label>
                  <input type="text" defaultValue={(metadata.hashtags || []).join(' ')} />
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: 'auto' }}>
                  <button className="btn" onClick={() => handleApprove(reel.url)}>Approve & Process</button>
                  <button className="btn btn-danger" onClick={() => handleReject(reel.url)}>Reject (Drop)</button>
                </div>
              </div>
            </div>
          );
        })}
        {reels.length === 0 && (
          <div className="glass-panel" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
            No videos awaiting review. The AI is still processing the backlog.
          </div>
        )}
      </div>

      <h2 style={{ marginTop: '60px' }}>Processed Videos Showcase ({finishedReels.length})</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '20px', marginBottom: '40px' }}>
        {finishedReels.map((reel) => {
          let metadata = {};
          try {
            metadata = JSON.parse(reel.ai_metadata || '{}');
          } catch(e) {}
          
          // Prioritize streaming URLs over raw GCS links
          const videoUrl = reel.firebase_url || reel.hls_cdn_url || (reel.gcs_uri ? `/api/video?gcs_uri=${encodeURIComponent(reel.gcs_uri)}` : '');
          
          return (
            <div key={reel.url} className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <video 
                src={videoUrl} 
                controls 
                style={{ width: '100%', aspectRatio: '9/16', borderRadius: '8px', background: '#000', objectFit: 'cover' }} 
                preload="metadata"
              />
              <div style={{ fontSize: '0.9rem', fontWeight: 'bold' }}>
                {reel.title || 'Untitled Video'}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                {metadata.caption || 'No caption available'}
              </div>
              <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem' }}>
                <span style={{ padding: '4px 8px', background: 'var(--accent-color)', borderRadius: '12px', color: '#fff' }}>
                  {reel.state.replace('RELAYED_TO_', '').replace('SYNCED_TO_', '')}
                </span>
                <a href={videoUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-color)', textDecoration: 'none' }}>
                  Open Link ↗
                </a>
              </div>
            </div>
          );
        })}
        {finishedReels.length === 0 && (
          <div className="glass-panel" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', gridColumn: '1 / -1' }}>
            No processed videos yet.
          </div>
        )}
      </div>
    </div>
  );
}
