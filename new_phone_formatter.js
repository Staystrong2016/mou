        // Formatar telefone: (XX) XXXXX-XXXX ou (XX) XXXX-XXXX
        function formatPhone(phone) {
            if (!phone) return 'Telefone não disponível';
            
            // Remove qualquer caractere que não seja número
            phone = phone.replace(/\D/g, '');
            
            // Registra o telefone original para debugging
            console.log("Telefone para formatação:", phone, "Comprimento:", phone.length);
            
            // Se começar com 55 e tiver mais de 11 dígitos (código do país Brasil), remove
            if (phone.startsWith('55') && phone.length > 11) {
                phone = phone.substring(2);
                console.log("Telefone após remover código do país:", phone, "Comprimento:", phone.length);
            }
            
            // Formata com base no comprimento
            if (phone.length === 11) {
                // Telefone celular com DDD (11 dígitos): (XX) XXXXX-XXXX
                return phone.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
            } else if (phone.length === 10) {
                // Telefone fixo com DDD (10 dígitos): (XX) XXXX-XXXX
                return phone.replace(/(\d{2})(\d{4})(\d{4})/, '($1) $2-$3');
            } else if (phone.length === 9) {
                // Apenas celular sem DDD (9 dígitos): XXXXX-XXXX
                return phone.replace(/(\d{5})(\d{4})/, '$1-$2');
            } else if (phone.length === 8) {
                // Apenas telefone fixo sem DDD (8 dígitos): XXXX-XXXX
                return phone.replace(/(\d{4})(\d{4})/, '$1-$2');
            } else {
                // Se não se encaixar em nenhum formato padrão, retorna como está
                return phone;
            }
        }
