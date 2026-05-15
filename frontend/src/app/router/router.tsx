import { createBrowserRouter, Navigate } from 'react-router'
import { AppShell } from '@/widgets/app-shell'
import { LandingPage } from '@/pages/landing'
import { LoginPage } from '@/pages/login'
import { RegistroPage } from '@/pages/registro'
import { RecuperarSenhaPage } from '@/pages/recuperar-senha'
import { VerificarEmailPage } from '@/pages/verificar-email'
import { RedefinirSenhaPage } from '@/pages/redefinir-senha'
import { AppHomePage } from '@/pages/app-home'
import { ProspeccaoPage } from '@/pages/prospeccao'
import { PipelinePage } from '@/pages/pipeline'
import { ListasPage } from '@/pages/listas'
import { RelatoriosPage } from '@/pages/relatorios'
import { ConfiguracoesPage } from '@/pages/configuracoes'
import { NotFoundPage } from '@/pages/not-found'
import { ProtectedRoute } from './ProtectedRoute'
import { RouteErrorBoundary } from './RouteErrorBoundary'

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/login', element: <LoginPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/registro', element: <RegistroPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/recuperar-senha', element: <RecuperarSenhaPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/verificar-email', element: <VerificarEmailPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/redefinir-senha', element: <RedefinirSenhaPage />, errorElement: <RouteErrorBoundary /> },
  {
    path: '/app',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/app/inicio" replace /> },
          { path: 'inicio', element: <AppHomePage /> },
          { path: 'prospeccao', element: <ProspeccaoPage /> },
          { path: 'pipeline', element: <PipelinePage /> },
          { path: 'listas', element: <ListasPage /> },
          { path: 'relatorios', element: <RelatoriosPage /> },
          { path: 'configuracoes', element: <ConfiguracoesPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])
