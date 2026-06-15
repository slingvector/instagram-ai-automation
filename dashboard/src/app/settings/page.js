'use client';
import { useEffect, useState } from 'react';
import { Save, UserPlus, Settings2, FileCode2, Command } from 'lucide-react';

export default function SettingsPage() {
  const [prompts, setPrompts] = useState({});
  const [env, setEnv] = useState({});
  const [loading, setLoading] = useState(true);

  // Registration state
  const [regUsername, setRegUsername] = useState('');
  const [regNiche, setRegNiche] = useState('art-erotica');
  const [regManifest, setRegManifest] = useState('art_erotica_manifest.yaml');
  const [regMessage, setRegMessage] = useState('');

  // Manifest Editor state
  const [selectedManifest, setSelectedManifest] = useState('indian_models_manifest.yaml');
  const [manifestContent, setManifestContent] = useState('');

  const fetchManifest = async (filename) => {
    try {
      const res = await fetch(`/api/config/manifest/read?file=${filename}`);
      const data = await res.json();
      if (data.content) {
        setManifestContent(data.content);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    async function fetchData() {
      try {
        const pRes = await fetch('/api/config/prompts');
        const pData = await pRes.json();
        setPrompts(pData.prompts || {});

        const eRes = await fetch('/api/config/env');
        const eData = await eRes.json();
        setEnv(eData.env || {});
        
        if (eData.env && eData.env.DISCOVERY_MANIFEST) {
          setSelectedManifest(eData.env.DISCOVERY_MANIFEST);
          await fetchManifest(eData.env.DISCOVERY_MANIFEST);
        } else {
          await fetchManifest(selectedManifest);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const handlePromptSave = async (key) => {
    await fetch('/api/config/prompts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, prompt: prompts[key] })
    });
    alert('Prompt saved successfully!');
  };

  const handleEnvSave = async (key, value) => {
    await fetch('/api/config/env', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value })
    });
    setEnv({ ...env, [key]: value });
  };

  const handleRegistration = async (e) => {
    e.preventDefault();
    setRegMessage('Adding creator...');
    try {
      const res = await fetch('/api/config/manifest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: regUsername, niche: regNiche, manifestFile: regManifest })
      });
      const data = await res.json();
      setRegMessage(data.message || data.error);
      if (data.success) {
        setRegUsername('');
        if (selectedManifest === regManifest) {
          fetchManifest(regManifest);
        }
      }
    } catch (err) {
      setRegMessage('Failed to register.');
    }
  };

  const handleManifestSave = async () => {
    try {
      const res = await fetch('/api/config/manifest/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selectedManifest, content: manifestContent })
      });
      const data = await res.json();
      alert(data.message || 'Saved successfully');
    } catch (e) {
      alert('Failed to save manifest.');
    }
  };

  if (loading) return <div><h2 style={{ color: 'var(--text-secondary)' }}>Loading Configuration...</h2></div>;

  return (
    <div>
      <h1 style={{ marginBottom: '40px' }}>System Configuration</h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginBottom: '40px' }}>
        
        {/* Pipeline Controls Section */}
        <div className="glass-panel">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}><Settings2 size={20} color="var(--accent-color)"/> Pipeline Environment</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', fontSize: '0.9rem' }}>These .env settings are applied on the next pipeline daemon cycle.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label>LocalSend Enabled</label>
              <select value={env.LOCALSEND_ENABLED || 'False'} onChange={(e) => handleEnvSave('LOCALSEND_ENABLED', e.target.value)}>
                <option value="True">True</option>
                <option value="False">False</option>
              </select>
            </div>
            <div>
              <label>Reels Per Cycle</label>
              <input type="number" value={env.REELS_PER_CYCLE || 3} onChange={(e) => handleEnvSave('REELS_PER_CYCLE', e.target.value)} />
            </div>
            <div>
              <label>Active Manifest</label>
              <input type="text" value={env.DISCOVERY_MANIFEST || ''} onChange={(e) => {
                handleEnvSave('DISCOVERY_MANIFEST', e.target.value);
                setSelectedManifest(e.target.value);
                fetchManifest(e.target.value);
              }} />
            </div>
            <div>
              <label>Gap Between Reels (secs)</label>
              <input type="number" value={env.GAP_BETWEEN_REELS || 0} onChange={(e) => handleEnvSave('GAP_BETWEEN_REELS', e.target.value)} />
            </div>
          </div>
        </div>

        {/* Registration Section */}
        <div className="glass-panel">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}><UserPlus size={20} color="var(--success)"/> Target Registration</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', fontSize: '0.9rem' }}>Append new creators to a specific YAML manifest.</p>
          <form onSubmit={handleRegistration} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label>Instagram Username</label>
              <input required value={regUsername} onChange={(e) => setRegUsername(e.target.value)} type="text" placeholder="e.g. alphachanneling" />
            </div>
            <div>
              <label>Niche Category</label>
              <input required value={regNiche} onChange={(e) => setRegNiche(e.target.value)} type="text" />
            </div>
            <div>
              <label>Target Manifest File</label>
              <select value={regManifest} onChange={(e) => setRegManifest(e.target.value)}>
                <option value="hot_content_manifest.yaml">hot_content_manifest.yaml</option>
                <option value="art_erotica_manifest.yaml">art_erotica_manifest.yaml</option>
                <option value="kink_fetish_manifest.yaml">kink_fetish_manifest.yaml</option>
                <option value="indian_models_manifest.yaml">indian_models_manifest.yaml</option>
              </select>
            </div>
            <button className="btn" type="submit" style={{ marginTop: '8px' }}><UserPlus size={16}/> Register Target</button>
            {regMessage && <div style={{ color: 'var(--accent-color)', fontSize: '0.9rem', textAlign: 'center' }}>{regMessage}</div>}
          </form>
        </div>

      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '32px', marginBottom: '40px' }}>
        {/* Advanced Manifest Editor */}
        <div className="glass-panel">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}><FileCode2 size={20} color="var(--warning)"/> Advanced Manifest Editor</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '16px', fontSize: '0.9rem' }}>Edit the full YAML manifest files directly to remove targets or modify global filters.</p>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
             <select value={selectedManifest} onChange={(e) => { setSelectedManifest(e.target.value); fetchManifest(e.target.value); }} style={{ width: '300px' }}>
                <option value="hot_content_manifest.yaml">hot_content_manifest.yaml</option>
                <option value="art_erotica_manifest.yaml">art_erotica_manifest.yaml</option>
                <option value="kink_fetish_manifest.yaml">kink_fetish_manifest.yaml</option>
                <option value="indian_models_manifest.yaml">indian_models_manifest.yaml</option>
              </select>
              <button className="btn" onClick={handleManifestSave}><Save size={16}/> Save Manifest</button>
          </div>
          <textarea 
            value={manifestContent} 
            onChange={(e) => setManifestContent(e.target.value)} 
            style={{ width: '100%', height: '300px', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85rem', lineHeight: '1.5', background: '#000', color: '#a3be8c' }}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '32px', marginBottom: '80px' }}>
        {/* Prompt Management Section */}
        <div className="glass-panel">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}><Command size={20} color="var(--accent-color)"/> AI Prompt Management</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '32px', fontSize: '0.9rem' }}>Modify the core system prompts used by Vertex AI and Ollama for analysis and copywriting.</p>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            {['video_analysis', 'roi_detection', 'transcription_and_vibe', 'relevance_filter'].map(key => (
              <div key={key} style={{ background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '12px', border: '1px solid var(--glass-border)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px', color: '#fff', fontSize: '1rem', alignItems: 'center' }}>
                  {key.replace(/_/g, ' ').toUpperCase()}
                  <button onClick={() => handlePromptSave(key)} className="btn" style={{ padding: '6px 12px', fontSize: '0.8rem' }}><Save size={14}/> Save</button>
                </label>
                <textarea 
                  rows="6" 
                  value={prompts[key] || ''} 
                  onChange={(e) => setPrompts({ ...prompts, [key]: e.target.value })}
                  style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem' }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
}
