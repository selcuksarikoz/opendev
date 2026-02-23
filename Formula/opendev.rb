class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.0.1"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.0.1/opendev-macos-arm64.tar.gz"
      sha256 "8bf8441a60a3125490c890452ff0d75d245ba669ccee40a4bee050972e1c3710"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.0.1/opendev-macos-x86_64.tar.gz"
      sha256 "8936134c2ad15fc4918141f7f0607b3daae005e91b8407093ee880db06bf314a"
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
