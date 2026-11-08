import { useAuth } from '../AuthContext'
import AuthForm from './AuthForm'

export default function Login() {
  const { login } = useAuth()
  return (
    <AuthForm
      title="Log in"
      submitLabel="Log in"
      fields={[
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'password', label: 'Password', type: 'password' },
      ]}
      onSubmit={({ email, password }) => login(email, password)}
      footer={{ text: "Don't have an account?", link: 'Sign up', to: '/register' }}
    />
  )
}
