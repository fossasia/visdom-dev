/* Copyright 2017-present, The Visdom Authors */
import { useCallback, useEffect, useState } from 'react';
import { useAuth, api } from '../context/AuthContext';
import { Building2, CreditCard, Gauge, Key, LineChart, Link2, LogOut, User, Users } from 'lucide-react';
import WorkspaceSwitcher from '../components/workspace/WorkspaceSwitcher';
import WorkspaceSettingsTab from '../components/workspace/WorkspaceSettingsTab';
import MembersTab from '../components/workspace/MembersTab';
import SharedLinksTab from '../components/workspace/SharedLinksTab';
import KeysTab from '../components/workspace/KeysTab';
import BillingTab from '../components/workspace/BillingTab';
import UsageTab from '../components/workspace/UsageTab';
import PendingInvitesBanner from '../components/workspace/PendingInvitesBanner';
import SuspendedBanner from '../components/workspace/SuspendedBanner';
import ProfileModal from '../components/ProfileModal';
import { readScoped, writeScoped } from '../utils/storage';
import { cachedGet, invalidate } from '../utils/requestCache';
import { pickActiveWorkspace, requestedWorkspaceSlug } from '../utils/activeWorkspace';

const TABS = [
  { id: 'workspaces', label: 'Workspaces', icon: Building2 },
  { id: 'members', label: 'Members', icon: Users },
  { id: 'keys', label: 'Keys & API', icon: Key },
  { id: 'shared', label: 'Shared Links', icon: Link2 },
  { id: 'usage', label: 'Usage', icon: Gauge },
  { id: 'billing', label: 'Billing', icon: CreditCard },
];

const WORKSPACE_SCOPED_TABS = new Set(['workspaces', 'members', 'shared']);
const TAB_IDS = new Set(TABS.map((tab) => tab.id));
const ACTIVE_TAB_STORAGE_KEY = 'dashboard-active-tab';
const DEFAULT_TAB = 'workspaces';

const Dashboard = () => {
  const { user, logout } = useAuth();
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspace, setActiveWorkspace] = useState(null);
  const [workspacesLoading, setWorkspacesLoading] = useState(true);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [activeTab, setActiveTab] = useState(() => {
    const stored = readScoped(ACTIVE_TAB_STORAGE_KEY, user?.id);
    return stored && TAB_IDS.has(stored) ? stored : DEFAULT_TAB;
  });

  const isAdmin = activeWorkspace?.role === 'admin';

  useEffect(() => {
    writeScoped(ACTIVE_TAB_STORAGE_KEY, user?.id, activeTab);
  }, [activeTab, user?.id]);

  const fetchWorkspaces = useCallback(async (force = false) => {
    setWorkspacesLoading(true);
    try {
      const data = await cachedGet('/workspaces', () => api.get('/workspaces').then((res) => res.data), { force });
      setWorkspaces(data);
      setActiveWorkspace((prev) =>
        pickActiveWorkspace(prev, data, requestedWorkspaceSlug(window.location.search))
      );
    } catch (err) {
      console.error(err);
    } finally {
      setWorkspacesLoading(false);
    }
  }, []);

  const fetchPendingInvites = useCallback(async () => {
    const key = '/workspaces/invites/pending';
    try {
      const data = await cachedGet(key, () => api.get(key).then((res) => res.data));
      setPendingInvites(data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
fetchWorkspaces();
    fetchPendingInvites();
  }, [fetchWorkspaces, fetchPendingInvites]);

  const handleInviteAccepted = (workspaceId) => {
    setPendingInvites((prev) => prev.filter((inv) => inv.workspace.id !== workspaceId));
    invalidate('/workspaces');
    fetchWorkspaces(true);
  };

  const handleInviteDeclined = (workspaceId) => {
    setPendingInvites((prev) => prev.filter((inv) => inv.workspace.id !== workspaceId));
    invalidate('/workspaces/invites/pending');
  };

  const handleWorkspaceCreated = (workspace) => {
    invalidate('/workspaces');
    setWorkspaces((prev) => [...prev, workspace]);
    setActiveWorkspace(workspace);
    setActiveTab(DEFAULT_TAB);
  };

  const handleWorkspaceUpdated = (workspace) => {
    invalidate('/workspaces');
    setWorkspaces((prev) =>
      prev.map((ws) => (ws.id === workspace.id ? workspace : ws))
    );
    setActiveWorkspace((prev) => (prev?.id === workspace.id ? workspace : prev));
  };

  const handleWorkspaceRemoved = (workspaceId) => {
    invalidate('/workspaces');
    setWorkspaces((prev) => prev.filter((ws) => ws.id !== workspaceId));
    setActiveWorkspace((prev) => (prev?.id === workspaceId ? null : prev));
    setActiveTab(DEFAULT_TAB);
  };

  const needsWorkspace = WORKSPACE_SCOPED_TABS.has(activeTab) && !activeWorkspace;
  const canVisualize = Boolean(activeWorkspace) && activeWorkspace.is_active !== false;

  return (
    <div className="gc-shell">
      <aside className="gc-sidebar">
        <a href="/" className="gc-logo" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <img src="/logo.svg" alt="Visdom Logo" style={{ height: '24px', width: '24px', borderRadius: '4px' }} />
          <span>visdom</span>
        </a>

        {!workspacesLoading && (
          <WorkspaceSwitcher
            workspaces={workspaces}
            activeWorkspace={activeWorkspace}
            onSwitch={setActiveWorkspace}
            onCreated={handleWorkspaceCreated}
            onWorkspaceUpdated={handleWorkspaceUpdated}
          />
        )}

        <nav className="gc-sidebar-nav">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={`gc-tab ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
                type="button"
              >
                <Icon size={15} />
                {tab.label}
              </button>
            );
          })}

          <a
            className="gc-tab gc-tab-viz"
            href={canVisualize ? `/vis/w/${activeWorkspace.slug}/` : undefined}
            aria-disabled={!canVisualize}
            onClick={(e) => {
              if (!canVisualize) e.preventDefault();
            }}
            title={
              canVisualize
                ? `Open ${activeWorkspace.name}'s visualizations`
                : activeWorkspace
                  ? `${activeWorkspace.name} is suspended`
                  : 'Select a workspace to open its visualizations'
            }
          >
            <LineChart size={15} />
            <span>Visualizations</span>
          </a>
        </nav>

        <div className="gc-sidebar-footer">
          <button
            onClick={() => setShowProfileModal(true)}
            className="gc-sidebar-user gc-truncate gc-sidebar-user-btn"
            type="button"
            title="Edit profile"
          >
            <User size={13} />
            <span className="gc-sidebar-user-email">{user?.username || user?.email}</span>
          </button>
          <button onClick={logout} className="gc-btn" type="button">
            <LogOut size={13} />
            Logout
          </button>
        </div>
      </aside>

      {showProfileModal && <ProfileModal onClose={() => setShowProfileModal(false)} />}

      <main className="gc-main">
        <PendingInvitesBanner
          invites={pendingInvites}
          currentUserId={user?.id}
          onAccepted={handleInviteAccepted}
          onDeclined={handleInviteDeclined}
        />

        <SuspendedBanner workspace={activeWorkspace} />

        {needsWorkspace ? (
          <section className="gc-panel">
            <div className="gc-empty">
              {workspaces.length === 0
                ? 'You don\'t have a workspace yet. Use "Add Workspace" in the sidebar to create your first one.'
                : 'Select a workspace from the sidebar to get started.'}
            </div>
          </section>
        ) : (
          <>
            {activeTab === 'workspaces' && activeWorkspace && (
              <WorkspaceSettingsTab
                workspace={activeWorkspace}
                isAdmin={isAdmin}
                currentUserId={user?.id}
                onDeleted={handleWorkspaceRemoved}
                onLeave={handleWorkspaceRemoved}
              />
            )}

            {activeTab === 'members' && activeWorkspace && (
              <MembersTab
                workspaceId={activeWorkspace.id}
                currentUserId={user?.id}
                isAdmin={isAdmin}
                ownerId={activeWorkspace.created_by}
                onOwnerChanged={handleWorkspaceUpdated}
              />
            )}

            {activeTab === 'keys' && (
              <KeysTab workspaces={workspaces} activeWorkspace={activeWorkspace} />
            )}

            {activeTab === 'shared' && activeWorkspace && (
              <SharedLinksTab workspaceId={activeWorkspace.id} isAdmin={isAdmin} />
            )}

            {activeTab === 'usage' && <UsageTab />}
            {activeTab === 'billing' && <BillingTab />}
          </>
        )}
      </main>
    </div>
  );
};

export default Dashboard;
