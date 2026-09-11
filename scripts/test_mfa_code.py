#!/usr/bin/env python3
import pyotp
import time
import os
import sys

def main():
    secret = os.getenv("MFA_SECRET", "TWWS5LSD6KP7FCAG2L52YO4PD2LJF2EC")
    totp = pyotp.TOTP(secret)
    now = time.time()
    remaining = 30 - int(now % 30)
    current_code = totp.now()

    print("=" * 65)
    print("🔍 Diagnóstico de Sincronização MFA / Google Authenticator")
    print("=" * 65)
    print(f"🔑 Chave configurada: {secret}")
    print(f"⏰ Hora do computador : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
    print(f"⏱️  Código do computador: \033[1;33m{current_code}\033[0m (expira em {remaining} segundos)")
    print("=" * 65)
    
    if len(sys.argv) > 1:
        user_input = sys.argv[1].strip()
    else:
        try:
            user_input = input("Digite o código de 6 dígitos que aparece no seu celular agora: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperação cancelada.")
            return

    if not user_input:
        print("Nenhum código digitado.")
        return

    if user_input == current_code:
        print("\n\033[1;32m✅ SUCESSO ABSOLUTO! O código do celular bateu 100% com o computador!\033[0m")
        return

    # Procura se há diferença de fuso / horário
    found_offset = None
    for offset in range(-10, 11):
        if totp.at(now + offset * 30) == user_input:
            found_offset = offset
            break

    if found_offset is not None:
        if found_offset < 0:
            print(f"\n\033[1;31m⚠️  DESALINHADO: O relógio do seu celular está ATRASADO em ~{abs(found_offset) * 30} segundos.\033[0m")
        else:
            print(f"\n\033[1;31m⚠️  DESALINHADO: O relógio do seu celular está ADIANTADO em ~{found_offset * 30} segundos.\033[0m")
        print("👉 Como resolver:")
        print("   No Android: Google Authenticator -> Menu -> Configurações -> 'Correção de horas para códigos' -> 'Sincronizar agora'.")
        print("   No iPhone : Ajustes -> Geral -> Data e Hora -> Ative 'Ajustar Automaticamente'.")
    else:
        print("\n\033[1;31m❌ O código digitado não corresponde a esta chave secreta.\033[0m")
        print("👉 Causas mais prováveis:")
        print("   1. Uma letra foi digitada errada na chave do celular.")
        print(f"      Chave exata: {secret}")
        print("   2. A data (dia/mês/ano) do celular e do computador não são as mesmas.")

if __name__ == "__main__":
    main()
