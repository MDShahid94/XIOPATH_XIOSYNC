import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'

const signup = vi.fn()

vi.mock('../../stores/authStore', () => ({
  default: () => ({ login: vi.fn(), signup }),
}))

describe('LoginPage public signup', () => {
  beforeEach(() => signup.mockReset())

  it('does not offer role or administrator selection', async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Create one' }))

    expect(screen.queryByLabelText('Role')).not.toBeInTheDocument()
    expect(screen.queryByText(/Admin/)).not.toBeInTheDocument()
  })
})
