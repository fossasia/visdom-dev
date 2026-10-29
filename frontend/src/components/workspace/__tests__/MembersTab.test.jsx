
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
    mockGet,
    mockPut,
    mockPost,
    mockDelete,
    mockConfirm,
    mockSuccess,
    mockError,
    mockInvalidate,
    mockCachedGet,
} = vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockPut: vi.fn(),
    mockPost: vi.fn(),
    mockDelete: vi.fn(),
    mockConfirm: vi.fn(),
    mockSuccess: vi.fn(),
    mockError: vi.fn(),
    mockInvalidate: vi.fn(),
    mockCachedGet: vi.fn(),
}));

vi.mock('../../../context/AuthContext', () => ({
    api: {
        get: mockGet,
        put: mockPut,
        post: mockPost,
        delete: mockDelete,
    },
}));

vi.mock('../../../context/ConfirmContext', () => ({
    useConfirm: () => mockConfirm,
}));

vi.mock('../../toast/useToast', () => ({
    useToast: () => ({
        success: mockSuccess,
        error: mockError,
    }),
}));

vi.mock('../../../utils/requestCache', () => ({
    cachedGet: mockCachedGet,
    invalidate: mockInvalidate,
}));

vi.mock('../InviteMemberModal', () => ({
    default: ({ onClose, onInvited }) => (
        <div>
            <span>Mock Invite Modal</span>
            <button onClick={onClose}>Close invite</button>
            <button
                onClick={() =>
                    onInvited({ user_id: 'new-user', email: 'new@example.com', role: 'member' })
                }
            >
                Simulate invitation
            </button>
        </div>
    ),
}));

import MembersTab from '../MembersTab';

const members = [
    {
        user_id: 'user-1',
        email: 'owner@example.com',
        role: 'admin',
        status: 'active',
    },
    {
        user_id: 'user-2',
        email: 'member@example.com',
        role: 'member',
        status: 'active',
    },
];

const pendingApprovalMember = {
    user_id: 'user-3',
    email: 'requester@example.com',
    role: 'member',
    status: 'pending_approval',
};

const pendingAcceptanceMember = {
    invite_id: 'invite-1',          // no user_id yet — uses invite_id as key
    user_id: null,
    email: 'invited@example.com',
    role: 'viewer',
    status: 'pending_acceptance',
};


describe('MembersTab', () => {
    beforeEach(() => {
        vi.clearAllMocks();

        mockCachedGet.mockImplementation((_key, fetcher) => fetcher());
        mockGet.mockResolvedValue({ data: members });
        mockConfirm.mockResolvedValue(true);
    });

    it('shows pending acceptance badge and Cancel invite button', async () => {
        mockCachedGet.mockResolvedValue([pendingAcceptanceMember]);

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        expect(
            await screen.findByText('Invite sent — awaiting acceptance'),
        ).toBeInTheDocument();
        expect(screen.getByText('Invited as: viewer')).toBeInTheDocument();
        expect(screen.getByTitle('Cancel invite')).toBeInTheDocument();
    });

    it('cancels a pending invite after confirmation', async () => {
        const user = userEvent.setup();

        mockCachedGet.mockResolvedValue([pendingAcceptanceMember]);
        mockDelete.mockResolvedValue({});

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('invited@example.com');
        await user.click(screen.getByTitle('Cancel invite'));

        await waitFor(() => {
            expect(mockDelete).toHaveBeenCalledWith(
                '/workspaces/workspace-1/invites/invite-1',
            );
        });
        expect(mockSuccess).toHaveBeenCalledWith('Invite cancelled.');
        await waitFor(() => {
            expect(screen.queryByText('invited@example.com')).not.toBeInTheDocument();
        });
    });

    it('transfers ownership to another member', async () => {
        const user = userEvent.setup();
        const mockOnOwnerChanged = vi.fn();

        mockPost.mockResolvedValue({ data: { owner_id: 'user-2' } });

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
                onOwnerChanged={mockOnOwnerChanged}
            />,
        );

        await screen.findByText('member@example.com');

        // Act: click the Crown (Make owner) button
        await user.click(screen.getByTitle('Make owner'));

        // Assert: correct API call
        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith(
                '/workspaces/workspace-1/owner',
                { user_id: 'user-2' },
            );
        });
        expect(mockOnOwnerChanged).toHaveBeenCalledWith({ owner_id: 'user-2' });
        expect(mockSuccess).toHaveBeenCalledWith('member@example.com now owns this workspace.');
    });

    it('does not transfer ownership when confirmation is declined', async () => {
        const user = userEvent.setup();
        mockConfirm.mockResolvedValue(false);

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('member@example.com');
        await user.click(screen.getByTitle('Make owner'));

        expect(mockPost).not.toHaveBeenCalled();
    });

    it('hides all management controls for non-admin users', async () => {
        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-2"
                isAdmin={false}
                ownerId="user-1"
            />,
        );

        await screen.findByText('owner@example.com');

        expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
        expect(screen.queryByTitle('Remove member')).not.toBeInTheDocument();
        expect(screen.queryByTitle('Make owner')).not.toBeInTheDocument();
    });



    it('shows pending approval badge and Approve/Decline buttons', async () => {
        // Arrange: API returns a member waiting for admin approval
        mockCachedGet.mockResolvedValue([pendingApprovalMember]);

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        // Assert: correct badge text is visible
        expect(
            await screen.findByText('Invitation sent — waiting approval'),
        ).toBeInTheDocument();
        expect(screen.getByText('Requested role: member')).toBeInTheDocument();

        // Assert: action buttons are rendered
        expect(screen.getByTitle('Approve request')).toBeInTheDocument();
        expect(screen.getByTitle('Decline request')).toBeInTheDocument();
    });

    it('approves a pending request and updates the member in the list', async () => {
        const user = userEvent.setup();

        // Arrange: member starts pending, API returns them as active after approval
        mockCachedGet.mockResolvedValue([pendingApprovalMember]);
        mockPost.mockResolvedValue({
            data: { ...pendingApprovalMember, status: 'active' },
        });

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('requester@example.com');

        // Act: click the Approve button
        await user.click(screen.getByTitle('Approve request'));

        // Assert: correct API endpoint called
        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith(
                '/workspaces/workspace-1/members/user-3/approve',
            );
        });
        expect(mockSuccess).toHaveBeenCalledWith('Request approved.');
    });

    it('declines a pending request after confirmation', async () => {
        const user = userEvent.setup();

        mockCachedGet.mockResolvedValue([pendingApprovalMember]);
        mockDelete.mockResolvedValue({});

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('requester@example.com');
        await user.click(screen.getByTitle('Decline request'));

        await waitFor(() => {
            expect(mockDelete).toHaveBeenCalledWith(
                '/workspaces/workspace-1/members/user-3',
            );
        });
        expect(mockSuccess).toHaveBeenCalledWith('Request declined.');
        await waitFor(() => {
            expect(screen.queryByText('requester@example.com')).not.toBeInTheDocument();
        });
    });




    it('shows a loading state before members load', () => {
        mockCachedGet.mockReturnValue(new Promise(() => { }));

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        expect(screen.getByText('Loading members...')).toBeInTheDocument();
    });

    it('renders members and identifies the current user and owner', async () => {
        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        expect(await screen.findByText('owner@example.com (you)')).toBeInTheDocument();
        expect(screen.getByText('member@example.com')).toBeInTheDocument();
        expect(screen.getByText('Owner')).toBeInTheDocument();
        expect(screen.getByText('Members (2)')).toBeInTheDocument();
    });



    it('shows an empty state when there are no members', async () => {
        mockCachedGet.mockResolvedValue([]);

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin={false}
                ownerId="user-1"
            />,
        );

        expect(
            await screen.findByText('No members in this workspace yet.'),
        ).toBeInTheDocument();
    });

    it('shows the Invite button only to admins', async () => {
        const { rerender } = render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin={false}
                ownerId="user-1"
            />,
        );

        await screen.findByText('owner@example.com (you)');
        expect(screen.queryByRole('button', { name: 'Invite' })).not.toBeInTheDocument();

        rerender(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        expect(screen.getByRole('button', { name: 'Invite' })).toBeInTheDocument();
    });

    it('opens the invite modal and adds an invited member', async () => {
        const user = userEvent.setup();

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await user.click(await screen.findByRole('button', { name: 'Invite' }));
        expect(screen.getByText('Mock Invite Modal')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'Simulate invitation' }));

        expect(await screen.findByText('new@example.com')).toBeInTheDocument();
        expect(screen.getByText('Members (3)')).toBeInTheDocument();
        expect(mockInvalidate).toHaveBeenCalledWith('/workspaces/workspace-1/members');
    });

    it('updates a member role successfully', async () => {
        const user = userEvent.setup();

        mockPut.mockResolvedValue({
            data: { ...members[1], role: 'viewer' },
        });

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('member@example.com');

        const roleSelect = screen.getAllByRole('combobox')[0];
        await user.selectOptions(roleSelect, 'viewer');

        await waitFor(() => {
            expect(mockPut).toHaveBeenCalledWith(
                '/workspaces/workspace-1/members/user-2',
                { role: 'viewer' },
            );
        });

        expect(mockSuccess).toHaveBeenCalledWith('Role updated.');
        expect(await screen.findByText('viewer')).toBeInTheDocument();
    });

    it('shows an error toast when a role update fails', async () => {
        const user = userEvent.setup();
        mockPut.mockRejectedValue({
            response: {
                data: { detail: 'Role update failed' },
            },
        });

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('member@example.com');

        await user.selectOptions(screen.getAllByRole('combobox')[0], 'viewer');

        await waitFor(() => {
            expect(mockError).toHaveBeenCalledWith(
                'Role update failed'
            );
        });
    });

    it('removes a member after confirmation', async () => {
        const user = userEvent.setup();
        mockDelete.mockResolvedValue({});

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('member@example.com');
        await user.click(screen.getAllByTitle('Remove member')[0]);

        await waitFor(() => {
            expect(mockDelete).toHaveBeenCalledWith(
                '/workspaces/workspace-1/members/user-2',
            );
        });

        expect(mockSuccess).toHaveBeenCalledWith('Member removed.');
        await waitFor(() => {
            expect(screen.queryByText('member@example.com')).not.toBeInTheDocument();
        });
    });

    it('does not remove a member when confirmation is declined', async () => {
        const user = userEvent.setup();
        mockConfirm.mockResolvedValue(false);

        render(
            <MembersTab
                workspaceId="workspace-1"
                currentUserId="user-1"
                isAdmin
                ownerId="user-1"
            />,
        );

        await screen.findByText('member@example.com');
        await user.click(screen.getAllByTitle('Remove member')[0]);

        expect(mockDelete).not.toHaveBeenCalled();
        expect(screen.getByText('member@example.com')).toBeInTheDocument();
    });
});
