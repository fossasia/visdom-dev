import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockPost, mockSuccess, mockOnClose, mockOnInvited } = vi.hoisted(() => ({
    mockPost: vi.fn(),
    mockSuccess: vi.fn(),
    mockOnClose: vi.fn(),
    mockOnInvited: vi.fn(),
}));

vi.mock('../../../context/AuthContext', () => ({
    api: {
        post: mockPost,
    },
}));

vi.mock('../../toast/useToast', () => ({
    useToast: () => ({
        success: mockSuccess,
    }),
}));

vi.mock('../../ModalPortal', () => ({
    default: ({ children }) => <div>{children}</div>,
}));

import InviteMemberModal from '../InviteMemberModal';

describe('InviteMemberModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders the invitation form with the default role', () => {
        render(
            <InviteMemberModal
                workspaceId="workspace-123"
                onClose={mockOnClose}
                onInvited={mockOnInvited}
            />,
        );

        expect(screen.getByText('Invite Collaborator')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('teammate@example.com')).toBeInTheDocument();
        expect(screen.getByRole('combobox')).toHaveValue('member');
        expect(screen.getByRole('button', { name: 'Send Invite' })).toBeInTheDocument();
    });

    it('submits a trimmed email and the selected role', async () => {
        const user = userEvent.setup();
        const invitedMember = { id: 'member-1', email: 'teammate@example.com' };

        mockPost.mockResolvedValue({ data: invitedMember });

        render(
            <InviteMemberModal
                workspaceId="workspace-123"
                onClose={mockOnClose}
                onInvited={mockOnInvited}
            />,
        );

        await user.type(
            screen.getByPlaceholderText('teammate@example.com'),
            '  teammate@example.com  ',
        );

        await user.selectOptions(screen.getByRole('combobox'), 'viewer');

        await user.click(screen.getByRole('button', { name: 'Send Invite' }));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith('/workspaces/workspace-123/members', {
                email: 'teammate@example.com',
                role: 'viewer',
            });
        });

        expect(mockSuccess).toHaveBeenCalledWith(
            'Invitation sent to teammate@example.com.',
        );
        expect(mockOnInvited).toHaveBeenCalledWith(invitedMember);
    });

    it('displays an error when the invitation API request fails', async () => {
        const user = userEvent.setup();

        mockPost.mockRejectedValue({
            response: {
                data: { detail: 'Invitation failed' },
            },
        });

        render(
            <InviteMemberModal
                workspaceId="workspace-123"
                onClose={mockOnClose}
                onInvited={mockOnInvited}
            />,
        );

        await user.type(
            screen.getByPlaceholderText('teammate@example.com'),
            'teammate@example.com',
        );

        await user.click(screen.getByRole('button', { name: 'Send Invite' }));

        expect(await screen.findByText('Invitation failed')).toBeInTheDocument();
        expect(mockOnInvited).not.toHaveBeenCalled();
    });

    it('calls onClose when the close button is clicked', async () => {
        const user = userEvent.setup();

        const { container } = render(
            <InviteMemberModal
                workspaceId="workspace-123"
                onClose={mockOnClose}
                onInvited={mockOnInvited}
            />,
        );

        await user.click(container.querySelector('.gc-modal-close'));

        expect(mockOnClose).toHaveBeenCalledOnce();
    });

    it('does not submit when the email field is empty', async () => {
        const user = userEvent.setup();

        render(
            <InviteMemberModal
                workspaceId="workspace-123"
                onClose={mockOnClose}
                onInvited={mockOnInvited}
            />,
        );

        // Do NOT type anything — submit immediately
        await user.click(screen.getByRole('button', { name: 'Send Invite' }));

        expect(mockPost).not.toHaveBeenCalled();
        expect(mockOnInvited).not.toHaveBeenCalled();
    });

    it('shows a loading state while the invite request is in progress', async () => {
        const user = userEvent.setup();

        // Never resolves — keeps the component in the submitting state
        mockPost.mockReturnValue(new Promise(() => {}));

        render(
            <InviteMemberModal
                workspaceId="workspace-123"
                onClose={mockOnClose}
                onInvited={mockOnInvited}
            />,
        );

        await user.type(
            screen.getByPlaceholderText('teammate@example.com'),
            'teammate@example.com',
        );

        await user.click(screen.getByRole('button', { name: 'Send Invite' }));

        // Button should now show loading text and be disabled
        expect(await screen.findByRole('button', { name: 'Sending Invite...' })).toBeDisabled();
    });
});