#!/usr/bin/env python3
"""
Script utilitário para gerar e configurar a autenticação de dois fatores (MFA / TOTP)
para o Administrador do Biskate Analytics (NFL Odds).
"""
import pyotp
import os
import sys

def main():
    print("=" * 60)
    print("🏈 Biskate Analytics — Gerador de Chave de Segurança MFA (TOTP)")
    print("=" * 60)
    
    existing_secret = os.getenv("MFA_SECRET")
    if existing_secret:
        print(f"\n⚠️  Atenção: Já existe um MFA_SECRET configurado no ambiente:")
        print(f"   Chave atual: {existing_secret}")
        choice = input("\nDeseja gerar uma nova chave? [s/N]: ").strip().lower()
        if choice != "s":
            secret = existing_secret
        else:
            secret = pyotp.random_base32()
    else:
        secret = pyotp.random_base32()

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name="admin",
        issuer_name="Biskate-NFL-Odds"
    )

    print("\n" + "—" * 60)
    print("📱 PASSO 1: Adicione esta chave ao seu aplicativo de autenticação")
    print("   (Google Authenticator, Microsoft Authenticator, Apple Passwords ou Authy)")
    print("—" * 60)
    print(f"\n🔑 SUA CHAVE SECRETA (Base32):")
    print(f"   \033[1;32m{secret}\033[0m")
    print("\nComo adicionar manualmente no Google Authenticator:")
    print("  1. Abra o Google Authenticator no celular.")
    print("  2. Toque no botão '+' e selecione 'Digitar chave de configuração'.")
    print("  3. Nome da conta: 'NFL Odds Admin'")
    print(f"  4. Sua chave: '{secret}'")
    print("  5. Tipo de chave: 'Com base no tempo'")
    print("  6. Toque em 'Adicionar'.")

    print("\n" + "—" * 60)
    print("⚙️ PASSO 2: Configure no seu arquivo .env ou no painel da nuvem:")
    print("—" * 60)
    print(f"MFA_SECRET={secret}")
    print("ADMIN_PASSWORD=SuaSenhaForteAqui123")
    print("READ_ONLY_MODE=true")

    print("\n" + "—" * 60)
    print("🧪 PASSO 3: Teste do código")
    print("—" * 60)
    print(f"Código atual gerado para validação: \033[1;33m{totp.now()}\033[0m")
    print("Verifique se o seu celular está mostrando exatamente este mesmo código de 6 dígitos.")
    print("=" * 60)

if __name__ == "__main__":
    main()
