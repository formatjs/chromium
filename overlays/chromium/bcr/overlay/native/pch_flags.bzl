"""Reproducible PCH metadata with normal Clang content validation."""

PCH_PRODUCER_FLAGS = [
    "-x",
    "c++-header",
    "--relocatable-pch",
    "-Xclang",
    "-fno-pch-timestamp",
    "-fpch-validate-input-files-content",
]

PCH_CONSUMER_FLAGS = ["-fpch-validate-input-files-content"]
