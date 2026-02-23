class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.1.1"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.1/opendev-macos-arm64.tar.gz"
      sha256 "ca41201c928009dc76669242badf182f5eaa4ed43c30bf59b0756cf9f9edb024"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.1/opendev-macos-x86_64.tar.gz"
      sha256 "26a60eeb1e1184c7a5c18ab379856cea3426e8c3ff3cb80b8b50c5a75ef95c59"
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
