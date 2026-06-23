################################################################################
# CktClaw — all-in-one Docker image
#
# Includes:
#   Open-source EDA  : Yosys, ABC, Verilator, OpenSTA, SymbiYosys, nextpnr-ice40
#   Design Agents    : digital-chip-design-agents (14-domain orchestrators)
#   AI4EDA Toolkit   : AI4EDA-OpenABC-Data-Toolkit
#   Python stack     : CktClaw + all dependencies
#
# Build:  docker build -t cktclaw .
# Run:    docker run -it --rm cktclaw
################################################################################

# ── Stage 1: build EDA tools from source ─────────────────────────────
FROM python:3.10-slim AS eda-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential clang bison flex libreadline-dev gawk \
        tcl-dev libffi-dev git pkg-config cmake \
        autoconf automake libtool swig \
        libboost-system-dev libboost-filesystem-dev \
        libboost-thread-dev libboost-program-options-dev \
        zlib1g-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Yosys
RUN git clone --depth 1 https://github.com/YosysHQ/yosys.git && \
    cd yosys && make config-gcc && make -j"$(nproc)" PREFIX=/opt/eda && \
    make install PREFIX=/opt/eda && \
    cd / && rm -rf /build/yosys

# ABC
RUN git clone --depth 1 https://github.com/berkeley-abc/abc.git && \
    cd abc && make -j"$(nproc)" abc && \
    cp abc /opt/eda/bin/abc && \
    cd / && rm -rf /build/abc

# Verilator
RUN git clone --depth 1 https://github.com/verilator/verilator.git && \
    cd verilator && autoconf && \
    ./configure --prefix=/opt/eda && make -j"$(nproc)" && make install && \
    cd / && rm -rf /build/verilator

# OpenSTA
RUN git clone --depth 1 https://github.com/The-OpenROAD-Project/OpenSTA.git && \
    cd OpenSTA && mkdir build && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/opt/eda && \
    make -j"$(nproc)" && make install && \
    cd / && rm -rf /build/OpenSTA

# SymbiYosys (sby — needs Yosys on PATH during install)
ENV PATH="/opt/eda/bin:${PATH}"
RUN git clone --depth 1 https://github.com/YosysHQ/sby.git && \
    cd sby && make install PREFIX=/opt/eda && \
    cd / && rm -rf /build/sby

# nextpnr-ice40 (needs icestorm for chipdb)
RUN git clone --depth 1 https://github.com/YosysHQ/icestorm.git && \
    cd icestorm && make -j"$(nproc)" PREFIX=/opt/eda && make install PREFIX=/opt/eda && \
    cd / && rm -rf /build/icestorm && \
    git clone --depth 1 https://github.com/YosysHQ/nextpnr.git && \
    cd nextpnr && cmake -DARCH=ice40 -DCMAKE_INSTALL_PREFIX=/opt/eda \
        -DICESTORM_INSTALL_PREFIX=/opt/eda . && \
    make -j"$(nproc)" && make install && \
    cd / && rm -rf /build/nextpnr


# ── Stage 2: final runtime image ─────────────────────────────────────
FROM python:3.10-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreadline8 libtcl8.6 libffi8 zlib1g git curl ca-certificates \
        gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built EDA binaries
COPY --from=eda-builder /opt/eda /opt/eda
ENV PATH="/opt/eda/bin:${PATH}"

# ── Clone external repos ─────────────────────────────────────────────
WORKDIR /opt

RUN git clone --depth 1 https://github.com/chuanseng-ng/digital-chip-design-agents.git

RUN git clone --depth 1 https://github.com/959AI994/AI4EDA-OpenABC-Data-Toolkit.git && \
    cd AI4EDA-OpenABC-Data-Toolkit && pip install --no-cache-dir -e .

RUN git clone --depth 1 https://github.com/Eriemon/verilog-generator.git

RUN git clone --depth 1 https://github.com/adeleempurpled290/FPGA-Agent-skills.git

# ── Install CktClaw ──────────────────────────────────────────────────
WORKDIR /opt/cktclaw

COPY pyproject.toml ./
RUN pip install --no-cache-dir prompt_toolkit rich pyyaml requests pydantic networkx

COPY . .
RUN pip install --no-cache-dir -e .

# Make wrapper scripts executable
RUN chmod +x eda_tools/wrappers/*.sh 2>/dev/null || true

# ── Environment variables ─────────────────────────────────────────────
ENV TERM=xterm-256color
ENV PYTHONUNBUFFERED=1
ENV CHIP_AGENTS_ROOT=/opt/digital-chip-design-agents/plugins
ENV AI4EDA_BIN=/opt/AI4EDA-OpenABC-Data-Toolkit/ai4eda-toolkit
ENV VERILOG_GENERATOR_ROOT=/opt/verilog-generator
ENV FPGA_AGENT_SKILLS_ROOT=/opt/FPGA-Agent-skills

WORKDIR /workspace

ENTRYPOINT ["cktclaw"]
