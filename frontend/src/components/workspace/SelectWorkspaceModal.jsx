/* Copyright 2017-present, The Visdom Authors */
import { useMemo, useState } from 'react';
import { Building2, Check, Plus, Search, Star, X } from 'lucide-react';
import { api, useAuth } from '../../context/AuthContext';
import { readScoped, writeScoped } from '../../utils/storage';
import { invalidate } from '../../utils/requestCache';
import ModalPortal from '../ModalPortal';
import CreateWorkspaceModal from './CreateWorkspaceModal';

const RECENT_KEY = 'recent-workspaces';
const MAX_RECENT = 8;
const THREE_HOURS_MS = 3 * 60 * 60 * 1000;

const getRecentIds = (userId) => {
  const items = readScoped(RECENT_KEY, userId, []);
  if (!Array.isArray(items)) return [];
  const now = Date.now();
  return items.filter((item) => now - item.timestamp <= THREE_HOURS_MS).map((item) => item.id);
};

const pushRecentId = (userId, id) => {
  const items = readScoped(RECENT_KEY, userId, []);
  const list = Array.isArray(items) ? items : [];
  const now = Date.now();
  const filtered = list.filter((item) => item.id !== id && now - item.timestamp <= THREE_HOURS_MS);
  writeScoped(RECENT_KEY, userId, [{ id, timestamp: now }, ...filtered].slice(0, MAX_RECENT));
};

const SECTIONS = [
  { id: 'recent', label: 'Recent' },
  { id: 'starred', label: 'Starred' },
  { id: 'all', label: 'All' },
];

const SelectWorkspaceModal = ({ workspaces, activeWorkspace, onClose, onSwitch, onCreated, onWorkspaceUpdated }) => {
  const [query, setQuery] = useState('');
  const [section, setSection] = useState('recent');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const { user } = useAuth();
  const [recentIds] = useState(() => getRecentIds(user?.id));

  const sectioned = useMemo(() => {
    if (section === 'starred') return workspaces.filter((ws) => ws.starred);
    if (section === 'recent') {
      const recent = recentIds.map((id) => workspaces.find((ws) => ws.id === id)).filter(Boolean);
      return recent.length > 0 ? recent : workspaces;
    }
    return workspaces;
  }, [workspaces, section, recentIds]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sectioned;
    return sectioned.filter(
      (ws) => ws.name.toLowerCase().includes(q) || ws.slug.toLowerCase().includes(q) || ws.id.toLowerCase().includes(q)
    );
  }, [sectioned, query]);

  const handleSwitch = (workspace) => {
    pushRecentId(user?.id, workspace.id);
    onSwitch(workspace);
    onClose();
  };

  const handleToggleStar = async (e, workspace) => {
    e.stopPropagation();
    try {
      const response = await api.patch(`/workspaces/${workspace.id}/star`, { starred: !workspace.starred });
      invalidate('/workspaces');
      onWorkspaceUpdated(response.data);
    } catch (err) {
      console.error('Failed to update starred workspace', err);
    }
  };

  const handleCreated = (workspace) => {
    setShowCreateModal(false);
    onCreated(workspace);
    onClose();
  };

  return (
    <ModalPortal onClose={onClose} wide aria-labelledby="select-workspace-modal-title">
      <div className="gc-modal-header">
        <span id="select-workspace-modal-title" className="gc-modal-title">Select a workspace</span>
        <div className="gc-flex-row-center">
          <button type="button" className="gc-btn gc-btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={14} />
            New Workspace
          </button>
          <button className="gc-modal-close" onClick={onClose} type="button" aria-label="Close">
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="gc-mb-lg relative">
        <Search
          size={14}
          className="gc-absolute-search-icon"
        />
        <input
          type="text"
          autoFocus
          className="gc-input gc-input-pl-search"
          placeholder="Search workspaces..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="gc-tabs-header-border">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSection(s.id)}
            className={`gc-tab-link-select ${section === s.id ? 'active' : ''}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="gc-ws-select-list">
        {filtered.length === 0 ? (
          <div className="gc-empty gc-border-none">
            {workspaces.length === 0
              ? "You don't belong to any workspaces yet."
              : section === 'starred'
              ? 'No starred workspaces yet — click the star on a workspace to pin it here.'
              : 'No workspaces match your search.'}
          </div>
        ) : (
          filtered.map((ws) => {
            const isActive = activeWorkspace?.id === ws.id;
            return (
              <button
                key={ws.id}
                type="button"
                onClick={() => handleSwitch(ws)}
                className={`gc-ws-select-row ${isActive ? 'active' : ''}`}
              >
                <span className="gc-flex-row-gap-sm-min-w">
                  <Building2 size={14} className="gc-shrink-0" />
                  <span className="gc-min-w-0">
                    <div className="gc-ws-item-name gc-truncate">
                      {ws.name}
                    </div>
                    <div className="gc-ws-item-slug gc-truncate">
                      {ws.slug} <span className="gc-font-mono">· {ws.id}</span>
                    </div>
                  </span>
                </span>

                <span className="gc-flex-row-gap-sm-min-w gc-shrink-0">
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(e) => handleToggleStar(e, ws)}
                    title={ws.starred ? 'Unstar workspace' : 'Star workspace'}
                    className={ws.starred ? 'gc-text-star-active' : 'gc-text-star-inactive'}
                  >
                    <Star size={15} fill={ws.starred ? '#f59e0b' : 'none'} />
                  </span>
                  {isActive && <Check size={15} className="gc-text-blue" />}
                </span>
              </button>
            );
          })
        )}
      </div>

      {showCreateModal && (
        <CreateWorkspaceModal onClose={() => setShowCreateModal(false)} onCreated={handleCreated} />
      )}
    </ModalPortal>
  );
};

export default SelectWorkspaceModal;
