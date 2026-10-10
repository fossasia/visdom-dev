/* Copyright 2017-present, The Visdom Authors */
import { useCallback, useEffect, useState } from 'react';
import { Check, Crown, UserPlus, Users, X } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { useConfirm } from '../../context/ConfirmContext';
import { useToast } from '../toast/useToast';
import InviteMemberModal from './InviteMemberModal';
import { cachedGet, invalidate } from '../../utils/requestCache';
import { ROLE_BADGE, parseApiError } from '../../utils/helpers';

const MEMBER_PAGE_SIZE = 100;

const MembersTab = ({ workspaceId, currentUserId, isAdmin, ownerId }) => {
  const [members, setMembers] = useState([]);
  const [totalMembers, setTotalMembers] = useState(0);
  const [nextCursor, setNextCursor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();

  const fetchMembers = useCallback(async () => {
    const key = `/workspaces/${workspaceId}/members?limit=${MEMBER_PAGE_SIZE}`;
    setLoading(true);
    try {
      const data = await cachedGet(key, () => api.get(key).then((res) => res.data));
      setMembers(data.items);
      setTotalMembers(data.total);
      setNextCursor(data.next_cursor);
    } catch (err) {
      console.error('Error fetching members', err);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const loadMoreMembers = async () => {
    if (!nextCursor || loadingMore) return;

    setLoadingMore(true);
    try {
      const response = await api.get(
        `/workspaces/${workspaceId}/members?limit=${MEMBER_PAGE_SIZE}&cursor=${encodeURIComponent(nextCursor)}`
      );
      setMembers((prev) => [...prev, ...response.data.items]);
      setTotalMembers(response.data.total);
      setNextCursor(response.data.next_cursor);
    } catch (err) {
      toast.error(parseApiError(err, 'Failed to load more members.'));
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
fetchMembers();
  }, [fetchMembers]);

  const handleInvited = async () => {
    setShowInvite(false);
    invalidate(`/workspaces/${workspaceId}/members`);
    await fetchMembers();
  };

  const handleRoleChange = async (userId, role) => {
    try {
      const response = await api.put(`/workspaces/${workspaceId}/members/${userId}`, { role });
      invalidate(`/workspaces/${workspaceId}/members`);
      setMembers((prev) => prev.map((m) => (m.user_id === userId ? response.data : m)));
      toast.success('Role updated.');
    } catch (err) {
      toast.error(parseApiError(err, 'Failed to update role.'));
    }
  };

  const handleRemove = async (userId) => {
    const ok = await confirm({
      title: 'Remove member',
      message: 'Remove this member from the workspace? They will lose access immediately.',
      confirmText: 'Remove',
      danger: true,
    });
    if (!ok) return;

    try {
      await api.delete(`/workspaces/${workspaceId}/members/${userId}`);
      invalidate(`/workspaces/${workspaceId}/members`);
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
      setTotalMembers((prev) => Math.max(0, prev - 1));
      toast.success('Member removed.');
    } catch (err) {
      toast.error(parseApiError(err, 'Failed to remove member.'));
    }
  };

  const handleDecline = async (member, opts) => {
    const ok = await confirm({
      title: opts.title,
      message: opts.message,
      confirmText: opts.confirmText,
      danger: true,
    });
    if (!ok) return;

    try {
      if (member.invite_id) {
        await api.delete(`/workspaces/${workspaceId}/invites/${member.invite_id}`);
      } else {
        await api.delete(`/workspaces/${workspaceId}/members/${member.user_id}`);
      }
      invalidate(`/workspaces/${workspaceId}/members`);
      setMembers((prev) => prev.filter((m) => m !== member));
      setTotalMembers((prev) => Math.max(0, prev - 1));
      toast.success(opts.successMessage);
    } catch (err) {
      toast.error(parseApiError(err, 'Failed to cancel.'));
    }
  };

  const handleApprove = async (userId) => {
    try {
      const response = await api.post(`/workspaces/${workspaceId}/members/${userId}/approve`);
      invalidate(`/workspaces/${workspaceId}/members`);
      setMembers((prev) => prev.map((m) => (m.user_id === userId ? response.data : m)));
      toast.success('Request approved.');
    } catch (err) {
      toast.error(parseApiError(err, 'Failed to approve request.'));
    }
  };

  return (
    <section className="gc-panel">
      <div className="gc-panel-header">
        <span className="gc-panel-title">
          <Users size={15} />
          Members ({totalMembers})
        </span>
        {isAdmin && (
          <button className="gc-btn gc-btn-primary" onClick={() => setShowInvite(true)} type="button">
            <UserPlus size={13} />
            Invite
          </button>
        )}
      </div>

      {loading ? (
        <div className="gc-empty">Loading members...</div>
      ) : members.length === 0 ? (
        <div className="gc-empty">No members in this workspace yet.</div>
      ) : (
        <div>
          {members.map((m) => {
            const isSelf = m.user_id === currentUserId;
            const isOwner = m.user_id === ownerId;
            const isPendingApproval = m.status === 'pending_approval';
            const isPendingAcceptance = m.status === 'pending_acceptance';
            const isPending = isPendingApproval || isPendingAcceptance;
            const canManage = isAdmin && !isSelf && !isOwner && !isPending;
            return (
              <div key={m.user_id || m.invite_id} className="gc-row">
                <div>
                  <div className="gc-row-main">{m.email}{isSelf && ' (you)'}</div>
                  <div className="gc-row-meta">
                    {isPendingApproval && (
                      <>
                        <span className="gc-badge gc-badge-viewer">Invitation sent — waiting approval</span>
                        <span>Requested role: {m.role}</span>
                      </>
                    )}
                    {isPendingAcceptance && (
                      <>
                        <span className="gc-badge gc-badge-viewer">Invite sent — awaiting acceptance</span>
                        <span>Invited as: {m.role}</span>
                      </>
                    )}
                    {!isPending && (
                      <span className={`gc-badge ${ROLE_BADGE[m.role] || 'gc-badge-member'}`}>{m.role}</span>
                    )}
                    {isOwner && (
                      <span className="gc-badge gc-badge-admin">
                        <Crown size={10} />
                        Owner
                      </span>
                    )}
                  </div>
                </div>

                {isAdmin && isPendingApproval && (
                  <div className="gc-flex-row-center">
                    <button
                      className="gc-btn gc-btn-icon gc-btn-icon-compact"
                      onClick={() => handleApprove(m.user_id)}
                      title="Approve request"
                      type="button"
                    >
                      <Check size={13} />
                    </button>
                    <button
                      className="gc-btn gc-btn-danger gc-btn-icon gc-btn-icon-compact"
                      onClick={() =>
                        handleDecline(m, {
                          title: 'Decline request',
                          message: 'Decline this join request?',
                          confirmText: 'Decline',
                          successMessage: 'Request declined.',
                        })
                      }
                      title="Decline request"
                      type="button"
                    >
                      <X size={13} />
                    </button>
                  </div>
                )}

                {isAdmin && isPendingAcceptance && (
                  <div className="gc-flex-row-center">
                    <button
                      className="gc-btn gc-btn-danger gc-btn-icon gc-btn-icon-compact"
                      onClick={() =>
                        handleDecline(m, {
                          title: 'Cancel invite',
                          message: 'Cancel this invite?',
                          confirmText: 'Cancel invite',
                          successMessage: 'Invite cancelled.',
                        })
                      }
                      title="Cancel invite"
                      type="button"
                    >
                      <X size={13} />
                    </button>
                  </div>
                )}

                {canManage && (
                  <div className="gc-flex-row-center">
                    <select
                      className="gc-select gc-select-compact"
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                    >
                      <option value="admin">Admin</option>
                      <option value="member">Member</option>
                      <option value="viewer">Viewer</option>
                    </select>
                    <button
                      className="gc-btn gc-btn-danger gc-btn-icon gc-btn-icon-compact"
                      onClick={() => handleRemove(m.user_id)}
                      title="Remove member"
                      type="button"
                    >
                      <X size={13} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!loading && nextCursor && (
        <div className="gc-row">
          <button
            className="gc-btn"
            disabled={loadingMore}
            onClick={loadMoreMembers}
            type="button"
          >
            {loadingMore ? 'Loading...' : `Load more (${members.length} of ${totalMembers})`}
          </button>
        </div>
      )}

      {showInvite && (
        <InviteMemberModal
          workspaceId={workspaceId}
          onClose={() => setShowInvite(false)}
          onInvited={handleInvited}
        />
      )}
    </section>
  );
};

export default MembersTab;
