/**
 * Calculadora integrada del navbar (Ukaro Abastos)
 *
 * Componente Alpine.js con dos pestañas:
 *   - "calc": calculadora básica de 4 operaciones
 *   - "usd":  conversor de USD físico (efectivo/calle) a USD BCV y Bs
 *
 * El factor de prima calle (cuánto vale 1 USD físico en USD BCV) NO se
 * guarda en el servidor: es un ajuste manual del día a día que cada
 * usuario define y que se recuerda solo en su navegador (localStorage).
 */
document.addEventListener('alpine:init', () => {
    Alpine.data('ukaroCalculator', (bcvRate) => ({
        // --- Estado general del widget ---
        open: false,
        tab: 'calc',

        // --- Calculadora básica ---
        display: '0',
        operator: null,
        firstOperand: null,
        waitingForSecondOperand: false,

        // --- Conversor USD físico -> BCV ---
        montoFisico: '',
        factor: '',
        tasaBcv: '',

        init() {
            this.tasaBcv = bcvRate !== null && bcvRate !== undefined ? String(bcvRate) : '';
            const factorGuardado = localStorage.getItem('ukaro_abastos_calc_factor');
            this.factor = factorGuardado || '';
            this.$watch('factor', (valor) => {
                if (valor) {
                    localStorage.setItem('ukaro_abastos_calc_factor', valor);
                }
            });
        },

        toggle() {
            this.open = !this.open;
        },

        // ---------- Calculadora básica ----------
        inputDigit(digit) {
            if (this.waitingForSecondOperand) {
                this.display = digit;
                this.waitingForSecondOperand = false;
            } else {
                this.display = this.display === '0' ? digit : this.display + digit;
            }
        },

        inputDecimal() {
            if (this.waitingForSecondOperand) {
                this.display = '0.';
                this.waitingForSecondOperand = false;
                return;
            }
            if (!this.display.includes('.')) {
                this.display += '.';
            }
        },

        backspace() {
            if (this.waitingForSecondOperand) return;
            this.display = this.display.length > 1 ? this.display.slice(0, -1) : '0';
        },

        clear() {
            this.display = '0';
            this.operator = null;
            this.firstOperand = null;
            this.waitingForSecondOperand = false;
        },

        toggleSign() {
            if (this.display === '0') return;
            this.display = this.display.startsWith('-') ? this.display.slice(1) : '-' + this.display;
        },

        percent() {
            this.display = String(parseFloat(this.display) / 100);
        },

        chooseOperator(nextOperator) {
            const inputValue = parseFloat(this.display);

            if (this.operator && this.waitingForSecondOperand) {
                this.operator = nextOperator;
                return;
            }

            if (this.firstOperand === null) {
                this.firstOperand = inputValue;
            } else if (this.operator) {
                const resultado = this.operate(this.firstOperand, inputValue, this.operator);
                this.display = String(resultado);
                this.firstOperand = resultado;
            }

            this.waitingForSecondOperand = true;
            this.operator = nextOperator;
        },

        operate(first, second, operator) {
            switch (operator) {
                case '+':
                    return this.redondear(first + second);
                case '-':
                    return this.redondear(first - second);
                case '×':
                    return this.redondear(first * second);
                case '÷':
                    return second === 0 ? 0 : this.redondear(first / second);
                default:
                    return second;
            }
        },

        redondear(numero) {
            // Evita errores de coma flotante tipo 0.1 + 0.2 = 0.30000000000000004
            return Math.round((numero + Number.EPSILON) * 1e10) / 1e10;
        },

        equals() {
            if (this.operator === null || this.firstOperand === null) return;
            const inputValue = parseFloat(this.display);
            const resultado = this.operate(this.firstOperand, inputValue, this.operator);
            this.display = String(resultado);
            this.firstOperand = null;
            this.operator = null;
            this.waitingForSecondOperand = false;
        },

        // ---------- Conversor USD físico -> BCV ----------
        get equivalenteBcv() {
            const monto = parseFloat(this.montoFisico);
            const factor = parseFloat(this.factor);
            if (isNaN(monto) || isNaN(factor)) return null;
            return monto * factor;
        },

        get montoBs() {
            const tasa = parseFloat(this.tasaBcv);
            if (this.equivalenteBcv === null || isNaN(tasa)) return null;
            return this.equivalenteBcv * tasa;
        },

        formatoUsd(valor) {
            if (valor === null || isNaN(valor)) return '—';
            return valor.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },

        formatoBs(valor) {
            if (valor === null || isNaN(valor)) return '—';
            return valor.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },
    }));
});
