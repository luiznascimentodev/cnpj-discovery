import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Prospecting } from './pages/Prospecting'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Prospecting />
    </QueryClientProvider>
  )
}
