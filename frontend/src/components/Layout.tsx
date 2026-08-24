import { NavLink, Outlet, useLocation, Link } from 'react-router-dom';
import './Layout.css';

function Layout() {
  const location = useLocation();

  return (
    <div className="layout-root">
      {/* Top Navigation */}
      <header className="top-nav">
        <div className="top-nav-inner container">
          <div className="nav-left">
            <Link to="/" className="brand-link">
              <span className="brand-symbol">◈</span>
              <span className="brand-text">GOD'S EYE</span>
            </Link>

            <nav className="nav-menu">
              <NavLink
                to="/"
                end
                className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}
              >
                Upload
              </NavLink>
              <NavLink
                to="/jobs"
                className={({ isActive }) => `nav-item ${isActive || location.pathname.startsWith('/jobs/') ? 'nav-item-active' : ''}`}
              >
                Jobs
              </NavLink>
            </nav>
          </div>

          <div className="nav-right">
            <div className="nav-status-indicator">
              <span className="status-dot"></span>
              <span className="status-label">LOCAL ENGINE</span>
            </div>
            <Link to="/" className="button-primary nav-cta">
              Upload Video
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content Floor */}
      <main className="main-content">
        <Outlet />
      </main>

      {/* Minimal Footer */}
      <footer className="footer">
        <div className="footer-inner container">
          <div className="footer-top">
            <div className="footer-brand">
              <span className="brand-text">GOD'S EYE</span>
              <p className="footer-tagline">
                AI-assisted spatial intelligence & 3D scene reconstruction from single-stream aerial drone video.
              </p>
            </div>
            <div className="footer-links-grid">
              <div className="footer-col">
                <span className="footer-col-title">PIPELINE</span>
                <span className="footer-link-text">Structure-from-Motion</span>
                <span className="footer-link-text">Learned Depth Fusion</span>
                <span className="footer-link-text">Semantic Bounding 3D</span>
                <span className="footer-link-text">Asset Generation</span>
              </div>
              <div className="footer-col">
                <span className="footer-col-title">OUTPUTS</span>
                <span className="footer-link-text">glTF / GLB Scene</span>
                <span className="footer-link-text">Scene Graph JSON</span>
                <span className="footer-link-text">Confidence Matrix</span>
                <span className="footer-link-text">Point Cloud PLY</span>
              </div>
              <div className="footer-col">
                <span className="footer-col-title">DEPLOYMENT</span>
                <span className="footer-link-text">Localhost Backend</span>
                <span className="footer-link-text">Modal GPU Offload</span>
                <span className="footer-link-text">Air-Gapped Ready</span>
              </div>
            </div>
          </div>
          <div className="footer-bottom">
            <span className="footer-copy">© 2026 God's Eye Spatial Intelligence. Local-first architecture.</span>
            <div className="footer-badges">
              <span className="badge-pill font-mono">v0.1.0-alpha</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Layout;
