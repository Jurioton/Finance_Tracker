import { useAuth } from '../AuthContext'
import AuthForm from './AuthForm'

export default function Register() {
  const { register } = useAuth()
  return (
    <AuthForm
      title="Create an account"
      submitLabel="Sign up"
      fields={[
        { name: 'name', label: 'Name' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'password', label: 'Password (min 6 characters)', type: 'password', minLength: 6 },
      ]}
      onSubmit={({ name, email, password }) => register(name, email, password)}
      footer={{ text: 'Already have an account?', link: 'Log in', to: '/login' }}
    />
  )
}
