class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.1.0"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.0/opendev-macos-arm64.tar.gz"
      sha256 "5cbab744f6a23dcf3c1fced8c1dda527f276106c36cce521c4ad07be4f866b14"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.0/opendev-macos-x86_64.tar.gz"
      sha256 "40a1522e7dc50bc41e062b7b504bdf5a360fdfbee6cf30276711839b1c6561a3"
    else
      odie "Unsupported macOS CPU."
    end
  else
    odie "Homebrew formula currently ships macOS binaries only."
  end

  def install
    bin.install "opendev"
  end

  test do
    assert_match "usage", shell_output("#{bin}/opendev --help 2>&1").downcase
  end
end
