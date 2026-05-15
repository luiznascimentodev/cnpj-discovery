_SEGMENT_DIVISIONS: list[tuple[str, set[int]]] = [
    ("Agropecuária, Pesca e Meio Rural", {1, 2, 3}),
    ("Extração e Mineração", {5, 6, 7, 8, 9}),
    ("Alimentos e Bebidas", {10, 11, 56}),
    ("Moda, Têxtil e Couro", {13, 14, 15}),
    ("Madeira, Papel e Impressão", {16, 17, 18}),
    ("Química, Farmacêutica e Plásticos", {19, 20, 21, 22}),
    ("Metalurgia, Máquinas e Equipamentos", {24, 25, 28, 33}),
    ("Eletrônicos, Veículos e Outras Indústrias", {23, 26, 27, 29, 30, 31, 32}),
    ("Energia, Água e Saneamento", {35, 36, 37, 38, 39}),
    ("Construção Civil", {41, 42, 43}),
    ("Comércio Atacadista", {46}),
    ("Comércio Varejista", {47}),
    ("Transporte, Correios e Logística", {49, 50, 51, 52, 53}),
    ("Hospedagem, Turismo e Eventos", {55, 79, 82}),
    ("Tecnologia, Software e Dados", {58, 59, 60, 61, 62, 63}),
    ("Serviços Financeiros e Seguros", {64, 65, 66}),
    ("Imóveis e Administração Patrimonial", {68}),
    ("Jurídico, Contábil e Gestão Empresarial", {69, 70}),
    ("Engenharia, Arquitetura e Pesquisa", {71, 72}),
    ("Marketing, Design e Serviços Profissionais", {73, 74}),
    ("Serviços Operacionais e Apoio a Empresas", {77, 78, 80, 81}),
    ("Educação", {85}),
    ("Saúde, Bem-estar e Assistência Social", {75, 86, 87, 88, 96}),
    ("Cultura, Esporte e Entretenimento", {90, 91, 92, 93}),
    ("Associações, Reparos e Serviços Pessoais", {94, 95}),
    ("Serviços Domésticos e Organismos Internacionais", {97, 99}),
    ("Administração Pública", {84}),
]

_SEGMENT_ORDER = [label for label, _ in _SEGMENT_DIVISIONS] + ["Outros"]


def _division(code: int) -> int:
    return code // 100000


def classify_cnae(code: int) -> str:
    div = _division(code)
    for label, divisions in _SEGMENT_DIVISIONS:
        if div in divisions:
            return label
    return "Outros"


def group_cnaes(cnaes: list[dict]) -> list[dict]:
    if not cnaes:
        return []
    groups: dict[str, list] = {}
    for cnae in cnaes:
        label = classify_cnae(cnae["codigo"])
        groups.setdefault(label, []).append(cnae)
    return [
        {"label": label, "cnaes": groups[label]}
        for label in _SEGMENT_ORDER
        if label in groups
    ]


def build_cnae_catalog(cnaes: list[dict]) -> dict:
    return {
        "all": cnaes,
        "segments": group_cnaes(cnaes),
    }
