class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.1.3"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.3/opendev-macos-arm64.tar.gz"
      sha256 "d27d47d35412a5d16b92bc2d75f259640c52482f50a2d4562f6e67b1e952146f"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.3/opendev-macos-x86_64.tar.gz"
      sha256 "9b8b28eb7c76be97b8a245d8c0bc7931dd9c8361e70f71c859d2fa8acf5002bc"
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
