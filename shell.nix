{ pkgs ? import <nixpkgs> {} }:

let
	unstable = import (pkgs.fetchFromGitHub {
		owner = "NixOS";
		repo = "nixpkgs";
		rev = "f00994e78cd39e6fc966f0c4103f908e63284780"; # nixos-unstable
		sha256 = "0kpnpja0pv4bk12iqia6avll31i85327p5drs2ycni14qa166y54";
	}) {};
in

pkgs.mkShell {
	buildInputs = with unstable; [
		(python311.withPackages (p: with p; [ black ]))
		pyright
	];

	shellHook = ''
		python -m venv .venv
		source .venv/bin/activate
		pip install -r requirements.txt
	'';
}
