import { useQuery } from '@tanstack/react-query'
import { getCnaes } from '@/shared/api'

export const useCnaes = () =>
  useQuery({
    queryKey: ['cnaes'],
    queryFn: getCnaes,
    staleTime: 1000 * 60 * 30,
  })
