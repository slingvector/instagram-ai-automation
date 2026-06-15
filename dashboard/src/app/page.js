'use client';
import { useEffect, useState } from 'react';
import { Play, ThumbsDown, Check, Flame, BarChart3, Clock, AlertTriangle } from 'lucide-react';

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [reels, setReels] = useState([]);
  const [finishedReels, setFinishedReels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const fetchShowcase = async (currentOffset = 0, append = false) => {
    try {
      const finishedRes = await fetch(`/api/reels?state=FINISHED&limit=12&offset=${currentOffset}`);
      const finishedData = await finishedRes.json();
      if (!finishedData.reels || finishedData.reels.length < 12) setHasMore(false);
      else setHasMore(true);

      if (append) {
        setFinishedReels(prev => {
          const newUrls = finishedData.reels.map(r => r.url);
          const filtered = prev.filter(r => !newUrls.includes(r.url));
          return [...filtered, ...finishedData.reels];
        });
      } else {
        setFinishedReels(finishedData.reels || []);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    async function fetchData() {
      try {
        const metricsRes = await fetch('/api/metrics');
        const metricsData = await metricsRes.json();
        setMetrics(metricsData);

        const reelsRes = await fetch('/api/reels?state=CAPTIONED');
        const reelsData = await reelsRes.json();
        setReels(reelsData.reels || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    fetchShowcase(0, false);
    
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

  const handleRating = async (url, rating) => {
    await fetch('/api/rating', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, rating })
    });
    setFinishedReels(prev => prev.map(r => {
      if (r.url === url) {
        let meta = {};
        try { meta = JSON.parse(r.ai_metadata || '{}'); } catch(e) {}
        meta.rating = rating;
        return { ...r, ai_metadata: JSON.stringify(meta) };
      }
      return r;
    }));
  };

  const loadMore = () => {
    const nextOffset = offset + 12;
    setOffset(nextOffset);
    fetchShowcase(nextOffset, true);
  };

  if (loading) return <div><h2 style={{ color: 'var(--text-secondary)' }}>Loading Dashboard...</h2></div>;

  return (
    <div>
      <h1 style={{ marginBottom: '40px' }}>Pipeline Overview</h1>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '24px', marginBottom: '56px' }}>
        <div className="glass-panel metric-card">
          <div className="metric-value">{metrics?.TOTAL || 0}</div>
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><BarChart3 size={16}/> Total Scanned</div>
        </div>
        <div className="glass-panel metric-card">
          <div className="metric-value" style={{ background: 'linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>{metrics?.DOWNLOADED || 0}</div>
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#60a5fa' }}><Clock size={16}/> Downloaded</div>
        </div>
        <div className="glass-panel metric-card">
          <div className="metric-value" style={{ background: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>{metrics?.CAPTIONED || 0}</div>
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fbbf24' }}><AlertTriangle size={16}/> Awaiting Review</div>
        </div>
        <div className="glass-panel metric-card">
          <div className="metric-value" style={{ background: 'linear-gradient(135deg, #34d399 0%, #10b981 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>{metrics?.MEDIA_PROCESSED || 0}</div>
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#34d399' }}><Check size={16}/> Processed</div>
        </div>
      </div>

      <h2 style={{ marginBottom: '24px' }}>Media Review Queue <span style={{ color: 'var(--accent-color)', fontSize: '1rem' }}>({reels.length} Items)</span></h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', marginBottom: '64px' }}>
        {reels.map((reel) => {
          let metadata = {};
          try { metadata = JSON.parse(reel.ai_metadata || '{}'); } catch(e) {}
          return (
            <div key={reel.url} className="glass-panel" style={{ display: 'flex', gap: '32px' }}>
              <div style={{ flex: '0 0 280px' }}>
                <video 
                  src={reel.gcs_uri ? `/api/video?gcs_uri=${encodeURIComponent(reel.gcs_uri)}` : ''} 
                  controls 
                  style={{ width: '100%', borderRadius: '12px', background: '#000', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }} 
                  preload="none"
                />
                <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>{reel.url}</div>
              </div>
              <div style={{ flex: '1', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div>
                  <label>Generated Caption</label>
                  <textarea rows="4" defaultValue={metadata.caption || ''} style={{ resize: 'vertical' }} />
                </div>
                <div>
                  <label>AI Hashtags</label>
                  <input type="text" defaultValue={(metadata.hashtags || []).join(' ')} />
                </div>
                <div style={{ display: 'flex', gap: '16px', marginTop: 'auto' }}>
                  <button className="btn" onClick={() => handleApprove(reel.url)} style={{ flex: 1 }}><Check size={18}/> Approve & Add to Render Queue</button>
                  <button className="btn btn-danger" onClick={() => handleReject(reel.url)} style={{ padding: '10px 24px' }}><ThumbsDown size={18}/></button>
                </div>
              </div>
            </div>
          );
        })}
        {reels.length === 0 && (
          <div className="glass-panel" style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
            <Play size={48} style={{ opacity: 0.2, marginBottom: '16px' }} />
            <div>No videos awaiting review. The AI is still processing the backlog.</div>
          </div>
        )}
      </div>

      <h2 style={{ marginBottom: '24px' }}>Processed Videos Showcase</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '32px', marginBottom: '40px' }}>
        {finishedReels.map((reel) => {
          let metadata = {};
          try { metadata = JSON.parse(reel.ai_metadata || '{}'); } catch(e) {}
          const videoUrl = reel.firebase_url || reel.hls_cdn_url || (reel.gcs_uri ? `/api/video?gcs_uri=${encodeURIComponent(reel.gcs_uri)}` : '');
          
          return (
            <div key={reel.url} className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px' }}>
              <video 
                src={videoUrl} 
                controls 
                style={{ width: '100%', aspectRatio: '9/16', borderRadius: '12px', background: '#000', objectFit: 'cover' }} 
                preload="metadata"
              />
              <div>
                <div style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '4px', fontFamily: 'Outfit' }}>{reel.title || 'Untitled'}</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{metadata.caption || 'No caption'}</div>
              </div>
              <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ padding: '6px 12px', background: 'var(--accent-glow)', borderRadius: '20px', color: '#fff', fontSize: '0.75rem', fontWeight: 'bold' }}>
                  {reel.state.replace('RELAYED_TO_', '').replace('SYNCED_TO_', '')}
                </span>
                <a href={videoUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-color)', fontSize: '0.85rem', fontWeight: '500' }}>Open Source ↗</a>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px', borderTop: '1px solid var(--glass-border)', paddingTop: '16px' }}>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', display: 'flex', gap: '12px' }}>
                  <span>👁️ {metadata.views_count || metadata.view_count || '?'}</span>
                  <span>❤️ {metadata.likes_count || metadata.like_count || '?'}</span>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button onClick={() => handleRating(reel.url, 'reject')} style={{ background: metadata.rating === 'reject' ? 'var(--danger)' : 'transparent', border: '1px solid var(--glass-border)', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}><ThumbsDown size={14}/></button>
                  <button onClick={() => handleRating(reel.url, 'awesome')} style={{ background: metadata.rating === 'awesome' ? 'var(--success)' : 'transparent', border: '1px solid var(--glass-border)', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}><Flame size={14}/></button>
                </div>
              </div>
            </div>
          );
        })}
        {finishedReels.length === 0 && (
          <div className="glass-panel" style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)', gridColumn: '1 / -1' }}>
            No processed videos yet.
          </div>
        )}
      </div>
      
      {hasMore && finishedReels.length > 0 && (
        <div style={{ textAlign: 'center', marginBottom: '80px' }}>
          <button className="btn" onClick={loadMore} style={{ padding: '14px 40px', fontSize: '1rem', borderRadius: '30px' }}>Load More Content</button>
        </div>
      )}
    </div>
  );
}
