'use client';
import "./globals.css";
import { LayoutDashboard, Activity, Settings, Film, ShieldAlert } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function RootLayout({ children }) {
  const pathname = usePathname();

  const navItems = [
    { name: 'Queue & Feed', path: '/', icon: Film },
    { name: 'Monitoring', path: '/monitoring', icon: Activity },
    { name: 'Settings & Config', path: '/settings', icon: Settings },
  ];

  return (
    <html lang="en">
      <head>
        <title>MCR AI Pipeline</title>
      </head>
      <body>
        <div className="app-container">
          <aside className="sidebar">
            <div className="sidebar-logo">
              <ShieldAlert size={28} color="#3b82f6" />
              <span>MCR Cortex</span>
            </div>
            
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.path;
                return (
                  <Link href={item.path} key={item.path} className={`nav-link ${isActive ? 'active' : ''}`}>
                    <Icon size={20} />
                    {item.name}
                  </Link>
                );
              })}
            </nav>

            <div style={{ marginTop: 'auto', padding: '32px', color: 'var(--text-secondary)', fontSize: '0.75rem', textAlign: 'center' }}>
              <div style={{ marginBottom: '8px' }}>System Status: <span style={{ color: 'var(--success)' }}>Online</span></div>
              <div>v2.0.0-edge</div>
            </div>
          </aside>

          <main className="main-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
