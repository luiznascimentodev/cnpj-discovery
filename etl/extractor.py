"""
Extractor ETL — leitura streaming de ZIPs da Receita Federal.

Técnica: abre o ZIP sem extrair para disco, lê o CSV interno linha a linha
e emite batches de N linhas como pl.DataFrame para o transformer/loader.

Nunca carrega o arquivo inteiro na memória.
"""
import io
import zipfile
from pathlib import Path
from typing import Generator

import polars as pl
from loguru import logger

# Buffer de leitura interno do stream descomprimido. 16 MB reduz chamadas de I/O
# no ZipExtFile sem pressionar memória — o batch em memória (500k linhas ~100 MB)
# é o fator dominante.
_READ_BUFFER_BYTES = 16 * 1024 * 1024


def stream_zip_as_batches(
    zip_path: Path,
    column_names: list[str],
    batch_size: int = 500_000,
) -> Generator[pl.DataFrame, None, None]:
    """
    Abre um arquivo ZIP da Receita Federal e emite batches de linhas como DataFrames Polars.

    Args:
        zip_path: Caminho para o arquivo .zip
        column_names: Lista de nomes de colunas (na ordem exata do CSV sem header)
        batch_size: Número de linhas por batch (default 500.000)

    Yields:
        pl.DataFrame com todas as colunas como pl.Utf8, pronto para o transformer

    Raises:
        ValueError: Se o ZIP não contiver nenhum arquivo CSV/sem extensão
        zipfile.BadZipFile: Se o arquivo ZIP estiver corrompido
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_name = _find_csv_entry(zf, zip_path)
        logger.info(f"Streaming {csv_name} from {zip_path.name} (batch_size={batch_size:,})")

        total_rows = 0
        batch_num = 0

        # io.BufferedReader sobre ZipExtFile agrupa leituras em blocos de
        # _READ_BUFFER_BYTES, reduzindo o número de chamadas de descompressão
        # zlib durante a iteração linha-a-linha.
        with io.BufferedReader(zf.open(csv_name), buffer_size=_READ_BUFFER_BYTES) as raw_file:
            buffer: list[bytes] = []

            for line in raw_file:
                buffer.append(line)
                if len(buffer) >= batch_size:
                    df = _parse_batch(buffer, column_names)
                    total_rows += len(df)
                    batch_num += 1
                    logger.debug(f"Batch {batch_num}: {len(df):,} rows (total: {total_rows:,})")
                    yield df
                    buffer.clear()

            if buffer:
                df = _parse_batch(buffer, column_names)
                total_rows += len(df)
                batch_num += 1
                yield df

        logger.success(f"Finished streaming {zip_path.name}: {total_rows:,} rows in {batch_num} batches")


def _find_csv_entry(zf: zipfile.ZipFile, zip_path: Path) -> str:
    """
    Localiza o arquivo CSV dentro do ZIP.

    Os ZIPs da RF contêm um arquivo sem extensão, com extensão .csv, ou com
    nomes compactados que terminam em marcadores como CNAECSV.
    Retorna o nome do primeiro arquivo válido encontrado.
    """
    entries = zf.namelist()

    # Primeiro: tenta encontrar arquivo .csv
    csv_entries = [e for e in entries if e.lower().endswith(".csv")]
    if csv_entries:
        return csv_entries[0]

    # Segundo: nomes internos atuais da RF, como F.K03200$Z.D60411.CNAECSV
    csv_marker_entries = [e for e in entries if "csv" in e.split("/")[-1].lower()]
    if csv_marker_entries:
        return csv_marker_entries[0]

    # Terceiro: arquivos sem extensão (padrão antigo da RF)
    no_ext_entries = [e for e in entries if "." not in e.split("/")[-1]]
    if no_ext_entries:
        return no_ext_entries[0]

    # Quarto: qualquer arquivo não-diretório — cobre nomes como ESTABELE
    file_entries = [e for e in entries if not e.endswith("/")]
    if file_entries:
        return file_entries[0]

    raise ValueError(
        f"No data file found in {zip_path.name}. "
        f"Available entries: {entries}"
    )


def _parse_batch(lines: list[bytes], column_names: list[str]) -> pl.DataFrame:
    """
    Converte uma lista de linhas bytes (Latin-1, delimitadas por ;) em pl.DataFrame.

    Todas as colunas ficam como pl.Utf8 — a tipagem acontece no transformer.
    """
    header = (";".join(column_names) + "\n").encode("latin-1")
    raw = header + b"".join(lines)
    raw = raw.replace(b"\x00", b"")  # null bytes são inválidos em UTF-8/PostgreSQL

    return pl.read_csv(
        io.BytesIO(raw),
        separator=";",
        encoding="latin-1",
        infer_schema_length=0,      # tudo como Utf8
        ignore_errors=True,         # linhas malformadas viram nulos
        truncate_ragged_lines=True, # linhas com colunas extras são truncadas
        has_header=True,
        new_columns=None,           # usa header sintético
    )
