from app.models import Source

# Cadastre aqui feeds RSS ou páginas de listagem. O sistema tolera falhas
# individuais: uma fonte fora do ar não derruba o radar inteiro.
SOURCES: list[Source] = [
    Source(name="Governo da Paraíba", url="https://paraiba.pb.gov.br/noticias", kind="html"),
    Source(name="Prefeitura de João Pessoa", url="https://www.joaopessoa.pb.gov.br/noticias/", kind="html"),
    Source(name="Polícia Militar da Paraíba", url="https://www.pm.pb.gov.br/noticias/", kind="html"),
    Source(name="Ministério Público da Paraíba", url="https://www.mppb.mp.br/index.php/noticias", kind="html"),
    Source(name="Tribunal de Justiça da Paraíba", url="https://www.tjpb.jus.br/noticias", kind="html"),
]
