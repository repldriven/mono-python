{
  description = "mono-python development environment";

  # The lint and format tools, and Docker. That is the whole toolchain:
  # nothing here is native and nothing generates code, so there is no prep
  # step to run before the workspace resolves.

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnsupportedSystem = true;
        };

        # Tessl CLI (plugin rules and skills). Pre-built binary from
        # install.tessl.io; darwin-arm64 to match this workspace's dev
        # machines.
        tessl = pkgs.stdenv.mkDerivation rec {
          pname = "tessl";
          version = "0.90.0";
          src = pkgs.fetchurl {
            url = "https://install.tessl.io/binaries/${version}/tessl-${version}-darwin-arm64.tar.gz";
            sha256 = "1v42hrlk0gfqr098b7irhdnmz72dvab8r58dskpmf257lfykf7x3";
          };
          sourceRoot = ".";
          installPhase = ''
            mkdir -p $out/bin
            install -m 755 tessl-${version}-darwin-arm64 $out/bin/tessl
          '';
        };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Matches requires-python in pyproject.toml; uv builds .venv from it.
            pkgs.python314
            pkgs.colima
            pkgs.docker
            pkgs.docker-credential-helpers
            pkgs.jq
            pkgs.just
            tessl
            pkgs.uv
          ];

          shellHook = ''
            # Colima/Docker configuration for testcontainers
            export DOCKER_HOST="unix://$HOME/.config/colima/default/docker.sock"
            export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE="/var/run/docker.sock"
            export TESTCONTAINERS_REUSE_ENABLE="TRUE"

            if ! colima status &>/dev/null; then
              echo "Docker not running — use 'just start-docker' to start"
            fi
            echo "mono-python environment loaded"
          '';
        };
      }
    );
}
