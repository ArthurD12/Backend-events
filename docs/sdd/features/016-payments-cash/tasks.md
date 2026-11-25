# Tasks: Pagos, comprobante, ingresos y egresos, flujo de caja

La migración se encadena al head de developer-b al momento de unir.

- [x] T-01 [ledger/domain] `INSTALLMENT`, número `PAG`, `PaymentVoid`, `CashMovement`, `MovementVoid` + tests
- [x] T-02 [ledger/app+infra] Repos, correlativo, migración (tablas, triggers append-only), `payment_voider`, consultas de suma para reporting + tests de integración
- [x] T-03 [commercial] `ContractBalance`, `RecordContractPayment`, `VoidContractPayment`, `GetContractAccount` con `FOR UPDATE` + tests; HU41/HU42 siguen verdes
- [x] T-04 [commercial] Comprobante PDF (`RenderPaymentReceipt`, ReportLab como `quote_pdf.py`) + test
- [x] T-05 [identity+reporting] Permiso `finance:read`; `GetCashFlow`, `GetEventResult` + tests
- [x] T-06 [presentation] Rutas del plan §4, `ContractOut`/`EventOut` con pagado y saldo + tests de API
- [x] T-07 [openapi+docs] `just openapi`; DOMAIN.md §6 y §11 (R-PAG-1..4)
- [ ] T-08 [frontend] Cuenta del contrato/evento, Caja, Flujo de caja, Resultado económico
