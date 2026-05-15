import { LegalLayout } from './LegalLayout'
import { LegalSection } from './LegalSection'

export function PrivacidadePage() {
  return (
    <LegalLayout title="Política de privacidade" lastUpdated="15 de maio de 2026">
      <p className="text-[var(--color-fg-secondary)]">
        Esta Política descreve como a plataforma <strong>CNPJ Discovery</strong>{' '}
        (a “Plataforma”) coleta, utiliza, armazena e protege dados pessoais, em
        conformidade com a Lei Geral de Proteção de Dados Pessoais (Lei nº 13.709/2018
        — “LGPD”).
      </p>

      <LegalSection id="controlador" title="1. Controlador dos dados">
        <p>
          O controlador dos dados pessoais tratados na Plataforma é{' '}
          <strong>Luiz Felippe Nascimento</strong> (“Operador”).
        </p>
        <p>
          Contato para assuntos de privacidade:{' '}
          <a
            href="https://wa.me/5541984821206"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-action)] underline-offset-2 hover:underline"
          >
            WhatsApp +55 (41) 98482-1206
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection id="dados-coletados" title="2. Dados pessoais tratados">
        <p>A Plataforma trata as seguintes categorias de dados pessoais dos usuários:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Dados de cadastro:</strong> nome e endereço de e-mail informados
            voluntariamente no registro.
          </li>
          <li>
            <strong>Credenciais de acesso:</strong> a senha é armazenada apenas em
            forma de hash criptográfico (Argon2id) — em nenhum momento o Operador tem
            acesso à senha em texto plano.
          </li>
          <li>
            <strong>Dados técnicos:</strong> endereço IP, identificador de sessão,
            navegador e sistema operacional, coletados nos eventos de autenticação para
            fins de segurança e auditoria.
          </li>
          <li>
            <strong>Cookies essenciais:</strong> cookie de sessão (<code>cnpj_session</code>) e
            cookie de proteção CSRF (<code>cnpj_csrf</code>), ambos estritamente
            necessários ao funcionamento autenticado.
          </li>
        </ul>
        <p>
          A Plataforma <strong>não</strong> coleta dados sensíveis nos termos do art. 5º,
          II da LGPD, nem trata dados de crianças e adolescentes.
        </p>
      </LegalSection>

      <LegalSection id="cnpj-publico" title="3. Dados públicos de pessoas jurídicas">
        <p>
          As informações cadastrais de empresas exibidas (CNPJ, razão social, CNAE,
          endereço, capital social etc.) são obtidas da base aberta da Receita Federal
          do Brasil e <strong>não constituem dados pessoais</strong> para os fins da
          LGPD (art. 5º, I), por se referirem a pessoas jurídicas.
        </p>
        <p>
          Quando registros públicos contiverem incidentalmente dados de pessoas
          naturais (por exemplo, nomes de sócios), tais dados são tratados com base
          em legítimo interesse para fins de prospecção comercial (art. 7º, IX da
          LGPD) e podem ser removidos a pedido do titular, conforme item 7 abaixo.
        </p>
      </LegalSection>

      <LegalSection id="finalidades" title="4. Finalidades do tratamento">
        <p>Os dados pessoais são tratados para as seguintes finalidades:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Criação e manutenção da conta do usuário;</li>
          <li>Autenticação, controle de sessão e proteção contra fraudes;</li>
          <li>Comunicação operacional (verificação de e-mail, recuperação de senha);</li>
          <li>Auditoria de eventos de segurança (login, registro, redefinição de senha);</li>
          <li>Cumprimento de obrigações legais e regulatórias aplicáveis.</li>
        </ul>
      </LegalSection>

      <LegalSection id="bases-legais" title="5. Bases legais (art. 7º da LGPD)">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Execução de contrato</strong> (inciso V): para viabilizar o cadastro,
            login e demais funcionalidades contratadas.
          </li>
          <li>
            <strong>Legítimo interesse</strong> (inciso IX): para auditoria de segurança,
            prevenção a fraudes e melhoria contínua da Plataforma.
          </li>
          <li>
            <strong>Cumprimento de obrigação legal</strong> (inciso II): quando exigido por
            autoridade competente.
          </li>
        </ul>
      </LegalSection>

      <LegalSection id="compartilhamento" title="6. Compartilhamento com terceiros">
        <p>
          Os dados pessoais não são vendidos ou compartilhados para fins comerciais.
          São utilizados, exclusivamente como operadores técnicos, os seguintes
          fornecedores:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Provedor de hospedagem (VPS):</strong> infraestrutura computacional
            onde a Plataforma é executada.
          </li>
          <li>
            <strong>Serviço de e-mail transacional</strong> (Resend ou equivalente):
            envio de mensagens de verificação e recuperação de senha.
          </li>
          <li>
            <strong>Serviço de captcha</strong> (hCaptcha): proteção contra abuso em
            formulários públicos, acionado apenas mediante rate-limit.
          </li>
        </ul>
        <p>
          Esses operadores tratam dados estritamente para a finalidade contratada e
          conforme suas próprias políticas de privacidade.
        </p>
      </LegalSection>

      <LegalSection id="direitos" title="7. Direitos do titular (art. 18 da LGPD)">
        <p>Como titular dos dados, você tem direito a:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Confirmação da existência de tratamento;</li>
          <li>Acesso aos dados;</li>
          <li>Correção de dados incompletos, inexatos ou desatualizados;</li>
          <li>
            Anonimização, bloqueio ou eliminação de dados desnecessários, excessivos ou
            tratados em desconformidade com a LGPD;
          </li>
          <li>Portabilidade dos dados a outro fornecedor;</li>
          <li>Eliminação dos dados pessoais tratados com base em consentimento;</li>
          <li>Informações sobre compartilhamento;</li>
          <li>Revogação do consentimento.</li>
        </ul>
        <p>
          As solicitações podem ser feitas via{' '}
          <a
            href="https://wa.me/5541984821206"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-action)] underline-offset-2 hover:underline"
          >
            WhatsApp +55 (41) 98482-1206
          </a>
          . O Operador responderá em até 15 dias úteis.
        </p>
      </LegalSection>

      <LegalSection id="retencao" title="8. Retenção e exclusão">
        <p>
          Os dados de cadastro são mantidos enquanto a conta estiver ativa. Após a
          exclusão da conta, os dados pessoais são removidos em até 30 dias, salvo
          obrigação legal de guarda (por exemplo, registros de acesso mantidos por 6
          meses, conforme art. 15 do Marco Civil da Internet).
        </p>
      </LegalSection>

      <LegalSection id="seguranca" title="9. Medidas de segurança">
        <p>
          O Operador adota medidas técnicas e organizacionais para proteger os dados
          pessoais, incluindo:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Senhas armazenadas com hash Argon2id e verificação contra vazamentos conhecidos (HIBP);</li>
          <li>Sessões em cookies HttpOnly com proteção CSRF (double-submit cookie);</li>
          <li>Rate-limiting por IP e por e-mail em endpoints sensíveis;</li>
          <li>Cabeçalhos de segurança (CSP, X-Frame-Options, HSTS quando aplicável);</li>
          <li>Auditoria de eventos de autenticação.</li>
        </ul>
        <p>
          Apesar dessas medidas, nenhum sistema é totalmente imune a incidentes.
          Em caso de incidente de segurança relevante, o Operador comunicará os
          titulares afetados e a ANPD, conforme art. 48 da LGPD.
        </p>
      </LegalSection>

      <LegalSection id="cookies" title="10. Cookies">
        <p>A Plataforma utiliza apenas cookies estritamente necessários ao funcionamento:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <code>cnpj_session</code> — identifica a sessão autenticada do usuário;
          </li>
          <li>
            <code>cnpj_csrf</code> — protege contra ataques de Cross-Site Request
            Forgery em ações autenticadas.
          </li>
        </ul>
        <p>
          Não há cookies de análise, publicidade ou rastreamento de terceiros nesta
          fase da Plataforma. Caso isso mude, esta Política será atualizada e o
          consentimento será solicitado conforme exigido por lei.
        </p>
      </LegalSection>

      <LegalSection id="transferencia" title="11. Transferência internacional">
        <p>
          Os dados pessoais são armazenados em infraestrutura localizada no Brasil.
          Eventuais transferências internacionais (por exemplo, uso de provedores de
          e-mail com servidores no exterior) ocorrem com base nas garantias previstas
          no art. 33 da LGPD.
        </p>
      </LegalSection>

      <LegalSection id="alteracoes-privacidade" title="12. Alterações desta Política">
        <p>
          Esta Política pode ser atualizada a qualquer tempo. A versão vigente será
          sempre a publicada nesta página, com data de atualização visível no topo.
          Mudanças materiais serão comunicadas por e-mail.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
