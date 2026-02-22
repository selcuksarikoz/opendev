class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.1.0"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.0/opendev-macos-arm64.tar.gz"
      sha256 "REPLACE_WITH_SHA256"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.0/opendev-macos-x86_64.tar.gz"
      sha256 "REPLACE_WITH_SHA256"
    else
      odie "Unsupported macOS CPU."
    end
  else
    odie "This formula currently ships macOS binaries only."
  end

  def install
    bin.install "opendev"
  end

  test do
    assert_match "usage", shell_output("#{bin}/opendev --help 2>&1").downcase
  end
end
