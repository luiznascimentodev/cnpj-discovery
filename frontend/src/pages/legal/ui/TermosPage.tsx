import { LegalLayout } from './LegalLayout'
import { LegalSection } from './LegalSection'

export function TermosPage() {
  return (
    <LegalLayout title="Termos de uso" lastUpdated="15 de maio de 2026">
      <p className="text-[var(--color-fg-secondary)]">
        Estes Termos regulam o uso da plataforma <strong>CNPJ Discovery</strong> (a
        “Plataforma”), operada por <strong>Luiz Felippe Nascimento</strong> (o
        “Operador”). Ao criar uma conta ou utilizar a Plataforma, você (“Usuário”)
        declara ter lido, compreendido e concordado integralmente com este documento.
      </p>

      <LegalSection id="objeto" title="1. Objeto">
        <p>
          A Plataforma oferece uma interface de pesquisa e organização de dados
          cadastrais públicos de pessoas jurídicas brasileiras, obtidos a partir da
          base aberta da Receita Federal do Brasil, com funcionalidades de filtros,
          pipeline de prospecção e exportação.
        </p>
      </LegalSection>

      <LegalSection id="aceitacao" title="2. Aceitação">
        <p>
          O cadastro de uma conta implica aceitação destes Termos e da Política de
          Privacidade. Se você não concorda com qualquer dispositivo, deve interromper
          imediatamente o uso da Plataforma.
        </p>
      </LegalSection>

      <LegalSection id="conta" title="3. Conta e credenciais">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            O Usuário fornece um e-mail válido e uma senha de no mínimo 12 caracteres
            durante o cadastro.
          </li>
          <li>
            O Usuário é o único responsável pela guarda e confidencialidade de suas
            credenciais. Toda atividade realizada com a conta presume-se feita pelo
            titular.
          </li>
          <li>
            É proibido compartilhar credenciais ou permitir o uso da conta por
            terceiros não autorizados.
          </li>
          <li>
            O Operador pode suspender ou encerrar a conta em caso de violação destes
            Termos, fraude, ou suspeita fundamentada de uso indevido.
          </li>
        </ul>
      </LegalSection>

      <LegalSection id="uso-permitido" title="4. Uso permitido">
        <p>O Usuário compromete-se a utilizar a Plataforma apenas para fins lícitos, incluindo:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Prospecção comercial B2B legítima;</li>
          <li>Pesquisa cadastral de empresas para fins próprios ou de seu empregador;</li>
          <li>Organização interna de oportunidades comerciais.</li>
        </ul>
      </LegalSection>

      <LegalSection id="uso-proibido" title="5. Uso proibido">
        <p>É expressamente vedado:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Realizar scraping automatizado, engenharia reversa, ou tentativas de
            acessar partes não públicas da Plataforma;
          </li>
          <li>
            Revender, sublicenciar, redistribuir ou expor os dados da Plataforma a
            terceiros como se fosse base própria;
          </li>
          <li>
            Utilizar os dados para fins discriminatórios, ilegais, ou em desacordo
            com a LGPD ou demais normas aplicáveis;
          </li>
          <li>
            Tentar comprometer a integridade, disponibilidade ou segurança da
            Plataforma (DoS, exploração de vulnerabilidades, etc.).
          </li>
        </ul>
      </LegalSection>

      <LegalSection id="dados" title="6. Natureza dos dados">
        <p>
          Os dados cadastrais de pessoas jurídicas exibidos na Plataforma têm origem
          em base pública da Receita Federal do Brasil. O Operador não garante
          completude, atualidade absoluta ou ausência de divergências, e
          recomenda-se a confirmação oficial em fontes primárias quando necessário
          para fins críticos.
        </p>
      </LegalSection>

      <LegalSection id="propriedade-intelectual" title="7. Propriedade intelectual">
        <p>
          O código-fonte, a marca, a identidade visual, os textos editoriais e a
          arquitetura da Plataforma pertencem ao Operador. Os dados cadastrais de
          pessoas jurídicas são públicos e não são objeto de propriedade do Operador.
        </p>
      </LegalSection>

      <LegalSection id="limitacao-responsabilidade" title="8. Limitação de responsabilidade">
        <p>
          A Plataforma é fornecida “no estado em que se encontra”. O Operador não
          responde por:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Eventuais indisponibilidades temporárias por manutenção ou falhas externas;</li>
          <li>
            Prejuízos comerciais decorrentes de decisões tomadas exclusivamente com base
            nos dados exibidos;
          </li>
          <li>
            Conteúdo de terceiros (por exemplo, serviços de e-mail, captcha, hospedagem)
            integrados à Plataforma, regidos por suas próprias políticas.
          </li>
        </ul>
      </LegalSection>

      <LegalSection id="rescisao" title="9. Rescisão">
        <p>
          O Usuário pode encerrar sua conta a qualquer momento solicitando exclusão
          via Contato. O Operador pode encerrar a conta em caso de violação destes
          Termos, mediante aviso prévio quando possível.
        </p>
      </LegalSection>

      <LegalSection id="alteracoes" title="10. Alterações">
        <p>
          Estes Termos podem ser atualizados a qualquer tempo. A versão vigente será
          sempre a publicada nesta página, com data de atualização visível no topo.
          Alterações materiais serão comunicadas por e-mail aos usuários ativos.
        </p>
      </LegalSection>

      <LegalSection id="lei-aplicavel" title="11. Lei aplicável e foro">
        <p>
          Estes Termos são regidos pela legislação brasileira. Fica eleito o foro da
          Comarca de Curitiba/PR para dirimir quaisquer controvérsias decorrentes
          deste documento, com renúncia a qualquer outro, por mais privilegiado que
          seja.
        </p>
      </LegalSection>

      <LegalSection id="contato-termos" title="12. Contato">
        <p>
          Dúvidas, solicitações ou notificações relacionadas a estes Termos podem ser
          enviadas via{' '}
          <a
            href="https://wa.me/5541984821206"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-action)] underline-offset-2 hover:underline"
          >
            WhatsApp
          </a>
          .
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
