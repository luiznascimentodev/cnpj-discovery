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


def stream_zip_as_batches(
    zip_path: Path,
    column_names: list[str],
    batch_size: int = 50_000,
) -> Generator[pl.DataFrame, None, None]:
    """
    Abre um arquivo ZIP da Receita Federal e emite batches de linhas como DataFrames Polars.

    Args:
        zip_path: Caminho para o arquivo .zip
        column_names: Lista de nomes de colunas (na ordem exata do CSV sem header)
        batch_size: Número de linhas por batch (default 50.000)

    Yields:
        pl.DataFrame com todas as colunas como pl.Utf8, pronto para o transformer

    Raises:
        ValueError: Se o ZIP não contiver nenhum arquivo CSV/sem extensão
        zipfile.BadZipFile: Se o arquivo ZIP estiver corrompido
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_name = _find_csv_entry(zf, zip_path)
        logger.info(f"Streaming {csv_name} from {zip_path.name} (batch_size={batch_size})")

        total_rows = 0
        batch_num = 0

        with zf.open(csv_name) as raw_file:
            buffer: list[bytes] = []

            for line in raw_file:
                buffer.append(line)
                if len(buffer) >= batch_size:
                    df = _parse_batch(buffer, column_names)
                    total_rows += len(df)
                    batch_num += 1
                    logger.debug(f"Batch {batch_num}: {len(df)} rows (total: {total_rows})")
                    yield df
                    buffer.clear()

            if buffer:
                df = _parse_batch(buffer, column_names)
                total_rows += len(df)
                batch_num += 1
                yield df

        logger.success(f"Finished streaming {zip_path.name}: {total_rows} total rows in {batch_num} batches")


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

    raise ValueError(
        f"No CSV or extensionless file found in {zip_path.name}. "
        f"Available entries: {entries}"
    )


def _parse_batch(lines: list[bytes], column_names: list[str]) -> pl.DataFrame:
    """
    Converte uma lista de linhas bytes (Latin-1, delimitadas por ;) em pl.DataFrame.

    Todas as colunas ficam como pl.Utf8 — a tipagem acontece no transformer.
    """
    # Adiciona header sintético para o polars saber os nomes das colunas
    header = (";".join(column_names) + "\n").encode("latin-1")
    raw = header + b"".join(lines)

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
