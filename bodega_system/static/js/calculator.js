/**
 * Calculadora integrada del navbar (Ukaro Abastos)
 *
 * Componente Alpine.js con dos pestañas:
 *   - "calc": calculadora básica de 4 operaciones (mouse o teclado)
 *   - "usd":  conversor de USD físico (efectivo/calle) a Bs y a USD BCV
 *
 * La tasa calle (cuánto vale hoy 1 USD físico en Bs) NO se guarda en el
 * servidor: es un ajuste manual del día a día que cada usuario define y que
 * se recuerda solo en su navegador (localStorage).
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

        // --- Conversor USD físico -> Bs / USD BCV ---
        montoFisico: '',
        tasaCalle: '',
        tasaBcv: '',

        init() {
            this.tasaBcv = bcvRate !== null && bcvRate !== undefined ? String(bcvRate) : '';

            const tasaCalleGuardada = localStorage.getItem('ukaro_abastos_calc_tasa_calle');
            this.tasaCalle = tasaCalleGuardada || '';
            this.$watch('tasaCalle', (valor) => {
                if (valor) {
                    localStorage.setItem('ukaro_abastos_calc_tasa_calle', valor);
                }
            });

            // Atajos de teclado: solo activos con el panel abierto y en la
            // pestaña de calculadora básica (la pestaña USD ya se maneja
            // sola, son inputs normales). Se ignora si el foco está en un
            // campo de texto de OTRA parte de la página (para no robarle
            // las teclas a un formulario de venta abierto detrás).
            this._onKeydown = (event) => {
                if (!this.open || this.tab !== 'calc') return;
                const tag = (event.target.tagName || '').toLowerCase();
                if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

                if (event.key >= '0' && event.key <= '9') {
                    this.inputDigit(event.key);
                    event.preventDefault();
                    return;
                }
                switch (event.key) {
                    case '.':
                    case ',':
                        this.inputDecimal();
                        event.preventDefault();
                        break;
                    case '+':
                        this.chooseOperator('+');
                        event.preventDefault();
                        break;
                    case '-':
                        this.chooseOperator('-');
                        event.preventDefault();
                        break;
                    case '*':
                        this.chooseOperator('×');
                        event.preventDefault();
                        break;
                    case '/':
                        this.chooseOperator('÷');
                        event.preventDefault();
                        break;
                    case '%':
                        this.percent();
                        event.preventDefault();
                        break;
                    case 'Enter':
                    case '=':
                        this.equals();
                        event.preventDefault();
                        break;
                    case 'Backspace':
                        this.backspace();
                        event.preventDefault();
                        break;
                }
                // Nota: Escape ya cierra el panel entero (ver @keydown.escape.window
                // en _calculator.html) — no se duplica acá para no pisarlo.
            };
            window.addEventListener('keydown', this._onKeydown);
        },

        destroy() {
            window.removeEventListener('keydown', this._onKeydown);
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

        // ---------- Conversor USD físico -> Bs / USD BCV ----------
        // El usuario ingresa directamente cuántos Bs vale hoy 1 USD físico
        // (tasa calle) — ya no se calcula a partir de un factor de prima.
        get montoBs() {
            const monto = parseFloat(this.montoFisico);
            const tasaCalle = parseFloat(this.tasaCalle);
            if (isNaN(monto) || isNaN(tasaCalle)) return null;
            return monto * tasaCalle;
        },

        get equivalenteBcv() {
            const tasa = parseFloat(this.tasaBcv);
            if (this.montoBs === null || isNaN(tasa) || tasa === 0) return null;
            return this.montoBs / tasa;
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
