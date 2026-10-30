# Template for Formula/specloop.rb in the KVTaniguchi/homebrew-tap repository.
# scripts/release prints the url and sha256 for each release.
class Specloop < Formula
  include Language::Python::Virtualenv

  desc "Keep a spec, the code, and the tests in lockstep with your coding agent"
  homepage "https://github.com/KVTaniguchi/specloop"
  url "https://files.pythonhosted.org/packages/source/s/specloop/specloop-VERSION.tar.gz"
  sha256 "SHA256"
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "specloop #{version}", shell_output("#{bin}/specloop --version")
  end
end
