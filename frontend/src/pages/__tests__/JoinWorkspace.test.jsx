/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import JoinWorkspace from '../JoinWorkspace';

const { mockPost, mockConfirm, mockToast, mockNavigate } = vi.hoisted(() => ({
    mockPost: vi.fn(),
    mockConfirm: vi.fn(),
    mockToast: {
        info: vi.fn(),
        success: vi.fn(),
        error: vi.fn(),
    },
    mockNavigate: vi.fn(),
}));

vi.mock('../../context/AuthContext', () => ({
    api: {
        post: mockPost,
    },
}));

vi.mock('../../context/ConfirmContext', () => ({
    useConfirm: () => mockConfirm,
}));

vi.mock('../../components/toast/useToast', () => ({
    useToast: () => mockToast,
}));

vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
        ...actual,
        useNavigate: () => mockNavigate,
        useParams: () => ({ linkId: 'test-link-123' }),
    };
});

describe('JoinWorkspace', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders the processing state panel', () => {
        mockConfirm.mockReturnValue(new Promise(() => {}));

        render(<JoinWorkspace />);

        expect(screen.getByText('Processing invitation...')).toBeInTheDocument();
    });

    it('prompts the user to confirm joining the workspace', async () => {
        mockConfirm.mockReturnValue(new Promise(() => {}));

        render(<JoinWorkspace />);

        expect(mockConfirm).toHaveBeenCalledWith({
            title: 'Join workspace',
            message:
                "You've been invited to join a workspace via a shared link. Request to join now? " +
                'An admin will need to approve your request before you get access.',
            confirmText: 'Request to join',
        });
    });

    it('navigates home when the user declines the invitation prompt', async () => {
        mockConfirm.mockResolvedValue(false);

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockPost).not.toHaveBeenCalled();
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });

    it('submits join request and shows success toast when approved', async () => {
        mockConfirm.mockResolvedValue(true);
        mockPost.mockResolvedValue({
            data: {
                workspace: { name: 'Alpha Lab' },
                role: 'member',
                status: 'pending',
            },
        });

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith('/workspaces/share/test-link-123/join', {
                password: null,
            });
            expect(mockToast.success).toHaveBeenCalledWith(
                'Request to join "Alpha Lab" as member sent — an admin needs to approve it before it appears in your workspaces.',
                { duration: 6000 },
            );
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });

    it('shows info toast when the user is already an active member', async () => {
        mockConfirm.mockResolvedValue(true);
        mockPost.mockResolvedValue({
            data: {
                workspace: { name: 'Alpha Lab' },
                role: 'member',
                status: 'active',
            },
        });

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockToast.info).toHaveBeenCalledWith('You\'re already a member of "Alpha Lab".');
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });

    it('prompts for password on 401 and joins when password is provided', async () => {
        mockConfirm.mockResolvedValueOnce(true); // initial join prompt
        mockPost.mockRejectedValueOnce({
            response: {
                status: 401,
                data: { detail: 'This shared link requires a password.' },
            },
        });
        mockConfirm.mockResolvedValueOnce('secretPass123'); // password prompt
        mockPost.mockResolvedValueOnce({
            data: {
                workspace: { name: 'Secure Workspace' },
                role: 'viewer',
                status: 'pending',
            },
        });

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockConfirm).toHaveBeenNthCalledWith(2, {
                title: 'Password required',
                message: 'This shared link is password protected. Enter the password to continue.',
                input: true,
                inputType: 'password',
                inputLabel: 'Password',
                confirmText: 'Join',
            });
            expect(mockPost).toHaveBeenNthCalledWith(2, '/workspaces/share/test-link-123/join', {
                password: 'secretPass123',
            });
            expect(mockToast.success).toHaveBeenCalledWith(
                'Request to join "Secure Workspace" as viewer sent — an admin needs to approve it before it appears in your workspaces.',
                { duration: 6000 },
            );
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });

    it('navigates home when password prompt is canceled', async () => {
        mockConfirm.mockResolvedValueOnce(true); // initial join prompt
        mockPost.mockRejectedValueOnce({
            response: {
                status: 401,
                data: { detail: 'This shared link requires a password.' },
            },
        });
        mockConfirm.mockResolvedValueOnce(null); // canceled password

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockConfirm).toHaveBeenCalledTimes(2);
            expect(mockPost).toHaveBeenCalledTimes(1);
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });

    it('displays error toast with API detail on failure', async () => {
        mockConfirm.mockResolvedValue(true);
        mockPost.mockRejectedValue({
            response: {
                status: 400,
                data: { detail: 'This invitation link has expired.' },
            },
        });

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockToast.error).toHaveBeenCalledWith('This invitation link has expired.');
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });

    it('displays fallback error toast when API error has no detail string', async () => {
        mockConfirm.mockResolvedValue(true);
        mockPost.mockRejectedValue(new Error('Network disconnected'));

        render(<JoinWorkspace />);

        await waitFor(() => {
            expect(mockToast.error).toHaveBeenCalledWith('This shared link is invalid.');
            expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
        });
    });
});
