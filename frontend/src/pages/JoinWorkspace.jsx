/* Copyright 2017-present, The Visdom Authors */
import { useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../context/AuthContext';
import { useConfirm } from '../context/ConfirmContext';
import { useToast } from '../components/toast/useToast';
import usePageTitle from '../hooks/usePageTitle';

const JoinWorkspace = () => {
  usePageTitle('Join workspace');
  const { linkId } = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const join = async (password) => {
      try {
        const response = await api.post(`/workspaces/share/${linkId}/join`, { password: password || null });
        const { workspace, role, status } = response.data;
        if (status === 'active') {
          toast.info(`You're already a member of "${workspace.name}".`);
        } else {
          toast.success(
            `Request to join "${workspace.name}" as ${role} sent — an admin needs to approve it before it appears in your workspaces.`,
            { duration: 6000 }
          );
        }
        navigate('/', { replace: true });
      } catch (err) {
        const detail = err.response?.data?.detail;

        if (err.response?.status === 401 && detail === 'This shared link requires a password.') {
          const password = await confirm({
            title: 'Password required',
            message: 'This shared link is password protected. Enter the password to continue.',
            input: true,
            inputType: 'password',
            inputLabel: 'Password',
            confirmText: 'Join',
          });
          if (password) {
            join(password);
          } else {
            navigate('/', { replace: true });
          }
          return;
        }

        toast.error(typeof detail === 'string' ? detail : 'This shared link is invalid.');
        navigate('/', { replace: true });
      }
    };

    const run = async () => {
      const wantsToJoin = await confirm({
        title: 'Join workspace',
        message:
          "You've been invited to join a workspace via a shared link. Request to join now? " +
          'An admin will need to approve your request before you get access.',
        confirmText: 'Request to join',
      });
      if (wantsToJoin) {
        join(null);
      } else {
        navigate('/', { replace: true });
      }
    };

    run();
  }, [linkId, navigate, confirm, toast]);

  return (
    <div className="auth-wrapper">
      <div className="visdom-panel auth-panel gc-text-center">
        Processing invitation...
      </div>
    </div>
  );
};

export default JoinWorkspace;
