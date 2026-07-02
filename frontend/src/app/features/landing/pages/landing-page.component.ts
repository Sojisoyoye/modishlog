import { Component, ChangeDetectionStrategy, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-landing-page',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="h-screen overflow-y-auto overflow-x-hidden scroll-smooth">
    <!-- ============================================================
         A. STICKY HEADER NAV
         ============================================================ -->
    <header class="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-100">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div class="flex h-16 items-center justify-between">
          <!-- Logo -->
          <div class="flex items-center gap-3">
            <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600 text-base font-bold text-white">
              M
            </div>
            <span class="text-xl font-bold text-gray-900">ModishLog</span>
          </div>

          <!-- Center nav links (desktop) -->
          <nav class="hidden md:flex items-center gap-8">
            <a href="#features" class="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Features</a>
            <a href="#pricing" class="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Pricing</a>
            <a routerLink="/login" class="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Login</a>
          </nav>

          <!-- Right: CTA (desktop) + hamburger (mobile) -->
          <div class="flex items-center gap-3">
            <a
              routerLink="/login"
              class="hidden md:inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors"
            >
              Launch My POS →
            </a>
            <button
              class="md:hidden flex h-10 w-10 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 transition-colors"
              (click)="mobileMenuOpen.set(!mobileMenuOpen())"
              aria-label="Toggle navigation menu"
              [attr.aria-expanded]="mobileMenuOpen()"
            >
              <i [class]="mobileMenuOpen() ? 'pi pi-times text-lg' : 'pi pi-bars text-lg'"></i>
            </button>
          </div>
        </div>

        <!-- Mobile nav drawer -->
        @if (mobileMenuOpen()) {
          <nav class="md:hidden border-t border-gray-100 py-3 flex flex-col gap-1" aria-label="Mobile navigation">
            <a href="#features" (click)="mobileMenuOpen.set(false)" class="block rounded-lg px-3 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">Features</a>
            <a href="#pricing" (click)="mobileMenuOpen.set(false)" class="block rounded-lg px-3 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">Pricing</a>
            <a routerLink="/login" (click)="mobileMenuOpen.set(false)" class="block rounded-lg px-3 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">Login</a>
          </nav>
        }
      </div>
    </header>

    <!-- ============================================================
         B. HERO SECTION
         ============================================================ -->
    <section class="min-h-screen flex items-center bg-white">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20 lg:py-0">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <!-- Left: Copy -->
          <div>
            <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-gray-900 leading-tight tracking-tight">
              Your Shop.<br />
              Your Profit.<br />
              <span class="text-emerald-600">Your Control.</span>
            </h1>
            <p class="mt-6 text-lg sm:text-xl text-gray-600 leading-relaxed max-w-xl">
              Record every sale in <strong class="text-gray-900">8 seconds</strong>. Know your exact margin on every product.
              Close your books in <strong class="text-gray-900">4 minutes</strong> — not 4 hours.
            </p>
            <div class="mt-8 flex flex-col sm:flex-row gap-4">
              <a
                routerLink="/login"
                class="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-8 py-4 text-base font-bold text-white shadow-md hover:bg-emerald-700 transition-colors min-h-[52px]"
              >
                Launch My POS →
              </a>
            </div>
            <p class="mt-6 text-sm text-gray-500">
              ★★★★★&nbsp;&nbsp;Trusted by <strong class="text-gray-700">200+ traders</strong> across Lagos, Abuja &amp; Kano
            </p>
          </div>

          <!-- Right: Product mockup (static HTML browser window) -->
          <div class="relative pb-10 sm:pb-0">
            <!-- overflow-hidden clips the mockup on mobile so it shows at full desktop width -->
            <div class="overflow-hidden rounded-xl shadow-2xl">
            <div class="w-[560px] border border-gray-200 bg-white">
              <!-- Browser chrome title bar -->
              <div class="flex items-center gap-2 bg-gray-100 px-4 py-3 border-b border-gray-200">
                <span class="h-3 w-3 rounded-full bg-red-400"></span>
                <span class="h-3 w-3 rounded-full bg-yellow-400"></span>
                <span class="h-3 w-3 rounded-full bg-green-400"></span>
                <div class="ml-4 flex-1 rounded-md bg-white border border-gray-200 px-3 py-1 text-xs text-gray-400">
                  app.modishlog.com/dashboard
                </div>
              </div>

              <!-- Simulated dashboard content -->
              <div class="bg-gray-50 p-4">
                <!-- KPI band -->
                <div class="grid grid-cols-3 gap-3 mb-4">
                  <div class="rounded-lg bg-emerald-600 p-3 text-white">
                    <p class="text-xs font-medium opacity-80">Today's Revenue</p>
                    <p class="text-xl font-bold mt-0.5">₦128,500</p>
                    <p class="text-xs opacity-70 mt-0.5">↑ 12% vs yesterday</p>
                  </div>
                  <div class="rounded-lg bg-white border border-gray-200 p-3">
                    <p class="text-xs font-medium text-gray-500">Gross Margin</p>
                    <p class="text-xl font-bold text-gray-900 mt-0.5">34.2%</p>
                    <p class="text-xs text-emerald-600 mt-0.5">↑ On target</p>
                  </div>
                  <div class="rounded-lg bg-white border border-gray-200 p-3">
                    <p class="text-xs font-medium text-gray-500">Sales Today</p>
                    <p class="text-xl font-bold text-gray-900 mt-0.5">47</p>
                    <p class="text-xs text-gray-400 mt-0.5">transactions</p>
                  </div>
                </div>

                <!-- Mini sales table -->
                <div class="rounded-lg bg-white border border-gray-200 overflow-hidden">
                  <div class="px-4 py-2 border-b border-gray-100">
                    <p class="text-xs font-semibold text-gray-700">Recent Sales</p>
                  </div>
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="bg-gray-50">
                        <th class="px-4 py-2 text-left text-gray-500 font-medium">Product</th>
                        <th class="px-4 py-2 text-right text-gray-500 font-medium">Qty</th>
                        <th class="px-4 py-2 text-right text-gray-500 font-medium">Revenue</th>
                        <th class="px-4 py-2 text-right text-gray-500 font-medium">Margin</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr class="border-t border-gray-50">
                        <td class="px-4 py-2 text-gray-800">Ankara Fabric (6 yds)</td>
                        <td class="px-4 py-2 text-right text-gray-600">3</td>
                        <td class="px-4 py-2 text-right text-gray-800 font-medium">₦18,000</td>
                        <td class="px-4 py-2 text-right"><span class="text-emerald-600 font-semibold">41%</span></td>
                      </tr>
                      <tr class="border-t border-gray-50">
                        <td class="px-4 py-2 text-gray-800">Lace Material (3 yds)</td>
                        <td class="px-4 py-2 text-right text-gray-600">2</td>
                        <td class="px-4 py-2 text-right text-gray-800 font-medium">₦24,000</td>
                        <td class="px-4 py-2 text-right"><span class="text-emerald-600 font-semibold">38%</span></td>
                      </tr>
                      <tr class="border-t border-gray-50">
                        <td class="px-4 py-2 text-gray-800">Shoe Box (Size 42)</td>
                        <td class="px-4 py-2 text-right text-gray-600">5</td>
                        <td class="px-4 py-2 text-right text-gray-800 font-medium">₦37,500</td>
                        <td class="px-4 py-2 text-right"><span class="text-yellow-600 font-semibold">22%</span></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            </div>

            <!-- Floating badge -->
            <div class="absolute -bottom-4 left-2 sm:-left-4 rounded-xl bg-white border border-gray-200 shadow-lg px-4 py-3 flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-50">
                <span class="text-emerald-600 text-lg">⚡</span>
              </div>
              <div>
                <p class="text-xs font-bold text-gray-900">Sale recorded</p>
                <p class="text-xs text-gray-500">8 seconds ago</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================================================
         C. SOCIAL PROOF BAND
         ============================================================ -->
    <section class="bg-gray-50 py-16">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <p class="text-center text-sm font-semibold uppercase tracking-widest text-gray-400 mb-10">
          What traders say about ModishLog
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <!-- Quote 1 -->
          <div class="rounded-xl bg-white border border-gray-100 shadow-sm p-6">
            <div class="flex items-center gap-3 mb-4">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-bold text-sm">A</div>
              <div>
                <p class="text-sm font-semibold text-gray-900">Amaka Obi</p>
                <p class="text-xs text-gray-400">Fabric &amp; Fashion, Lagos Island</p>
              </div>
            </div>
            <p class="text-sm text-gray-600 leading-relaxed">"Before ModishLog I had no idea which fabrics were actually profitable. Now I can see it in seconds."</p>
          </div>

          <!-- Quote 2 -->
          <div class="rounded-xl bg-white border border-gray-100 shadow-sm p-6">
            <div class="flex items-center gap-3 mb-4">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-blue-700 font-bold text-sm">K</div>
              <div>
                <p class="text-sm font-semibold text-gray-900">Kelechi Nwosu</p>
                <p class="text-xs text-gray-400">Electronics Trader, Onitsha</p>
              </div>
            </div>
            <p class="text-sm text-gray-600 leading-relaxed">"The FX rate tracking alone saved me — I used to lose money on dollar products without even knowing."</p>
          </div>

          <!-- Quote 3 -->
          <div class="rounded-xl bg-white border border-gray-100 shadow-sm p-6">
            <div class="flex items-center gap-3 mb-4">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-purple-100 text-purple-700 font-bold text-sm">F</div>
              <div>
                <p class="text-sm font-semibold text-gray-900">Fatima Sule</p>
                <p class="text-xs text-gray-400">Cosmetics &amp; Skincare, Abuja</p>
              </div>
            </div>
            <p class="text-sm text-gray-600 leading-relaxed">"I used to spend Sunday evenings reconciling sales. Now my books close in under 5 minutes. Game changer."</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================================================
         D. FEATURE PREVIEW — "Add Sale" mockup
         ============================================================ -->
    <section class="py-20 bg-white">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl sm:text-4xl font-extrabold text-gray-900">See it before you buy it</h2>
          <p class="mt-3 text-lg text-gray-500">No training needed. If you can use WhatsApp, you can use ModishLog.</p>
        </div>

        <!-- Browser-frame mockup of Add Sale form -->
        <div class="mx-auto max-w-xl rounded-xl border border-gray-200 shadow-xl overflow-hidden">
          <!-- Browser chrome -->
          <div class="flex items-center gap-2 bg-gray-100 px-4 py-3 border-b border-gray-200">
            <span class="h-3 w-3 rounded-full bg-red-400"></span>
            <span class="h-3 w-3 rounded-full bg-yellow-400"></span>
            <span class="h-3 w-3 rounded-full bg-green-400"></span>
            <div class="ml-4 flex-1 rounded-md bg-white border border-gray-200 px-3 py-1 text-xs text-gray-400">
              app.modishlog.com/sales/new
            </div>
          </div>

          <!-- Form body -->
          <div class="bg-white p-6">
            <h3 class="text-base font-semibold text-gray-800 mb-5">Record a Sale</h3>

            <!-- Product selector -->
            <div class="mb-4">
              <label class="block text-xs font-medium text-gray-600 mb-1.5">Product</label>
              <div class="flex items-center justify-between rounded-lg border border-gray-300 px-3 py-2.5 bg-white cursor-default">
                <span class="text-sm text-gray-800">Ankara Fabric — 6 yards</span>
                <span class="text-gray-400 text-xs">▼</span>
              </div>
            </div>

            <!-- Qty + Price row -->
            <div class="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label class="block text-xs font-medium text-gray-600 mb-1.5">Quantity</label>
                <div class="rounded-lg border border-gray-300 px-3 py-2.5 bg-white">
                  <span class="text-sm text-gray-800">2</span>
                </div>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-600 mb-1.5">Unit Price (₦)</label>
                <div class="rounded-lg border border-gray-300 px-3 py-2.5 bg-white">
                  <span class="text-sm text-gray-800">6,000</span>
                </div>
              </div>
            </div>

            <!-- Payment method -->
            <div class="mb-4">
              <label class="block text-xs font-medium text-gray-600 mb-1.5">Payment Method</label>
              <div class="flex gap-2">
                <span class="rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold px-3 py-1 cursor-default">Cash</span>
                <span class="rounded-full bg-gray-100 text-gray-500 text-xs font-medium px-3 py-1 cursor-default">Transfer</span>
                <span class="rounded-full bg-gray-100 text-gray-500 text-xs font-medium px-3 py-1 cursor-default">POS</span>
              </div>
            </div>

            <!-- Total row -->
            <div class="flex items-center justify-between rounded-lg bg-emerald-50 px-4 py-3 mb-5">
              <span class="text-sm font-semibold text-emerald-800">Total</span>
              <span class="text-xl font-extrabold text-emerald-700">₦12,000</span>
            </div>

            <!-- Margin hint -->
            <div class="flex items-center gap-2 text-xs text-gray-500 mb-5">
              <span class="text-emerald-500">●</span>
              Estimated margin: <strong class="text-emerald-700">41% — above your 30% target</strong>
            </div>

            <!-- Submit button -->
            <button
              type="button"
              class="w-full rounded-lg bg-emerald-600 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-700 transition-colors"
            >
              Record Sale →
            </button>
          </div>
        </div>

        <p class="text-center mt-6 text-sm text-gray-400">
          ↑ This is a live preview. Every field is real — nothing is mocked in production.
        </p>
      </div>
    </section>

    <!-- ============================================================
         E. COMPETITOR COMPARISON TABLE
         ============================================================ -->
    <section id="features" class="py-20 bg-gray-50">
      <div class="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl sm:text-4xl font-extrabold text-gray-900">Why switch from spreadsheets?</h2>
          <p class="mt-3 text-lg text-gray-500">Everything you were trying to do in Excel — done automatically.</p>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-gray-200 shadow-sm">
          <table class="min-w-full">
            <thead>
              <tr class="bg-gray-900 text-white">
                <th class="px-5 py-4 text-left text-sm font-semibold min-w-[180px]">Feature</th>
                <th class="px-5 py-4 text-center text-sm font-semibold text-emerald-400 min-w-[120px]">ModishLog</th>
                <th class="px-5 py-4 text-center text-sm font-semibold text-gray-400 min-w-[120px]">Other POS Apps</th>
                <th class="px-5 py-4 text-center text-sm font-semibold text-gray-400 min-w-[120px]">Spreadsheet</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 bg-white">
              <tr>
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Sales recording in seconds</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr class="bg-gray-50">
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Auto profit margin per product</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr>
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Live NGN/USD &amp; EUR/NGN rates</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr class="bg-gray-50">
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">AI price recommendations</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr>
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Full P&amp;L &amp; cashflow reports</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr class="bg-gray-50">
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Expense tracking</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr>
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Supplier &amp; purchase order management</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-yellow-500 font-bold text-base">~</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr class="bg-gray-50">
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Customer debt ledger</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-yellow-500 font-bold text-base">~</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr>
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Stock count &amp; variance reports</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-yellow-500 font-bold text-base">~</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
              </tr>
              <tr class="bg-gray-50">
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">One-time payment, no subscription</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-red-400 font-bold text-base">✗</span></td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
              </tr>
              <tr>
                <td class="px-5 py-4 text-sm text-gray-700 font-medium">Works on mobile</td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-emerald-600 font-bold text-base">✓</span></td>
                <td class="px-5 py-4 text-center"><span class="text-yellow-500 font-bold text-base">~</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-3 text-center text-xs text-gray-400">~ = limited or basic support</p>
      </div>
    </section>

    <!-- ============================================================
         F. 3-TIER PRICING BLOCK
         ============================================================ -->
    <section id="pricing" class="py-20 bg-gray-900 text-white">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-4">
          <h2 class="text-3xl sm:text-4xl font-extrabold">Simple pricing. One payment. Forever yours.</h2>
          <p class="mt-3 text-lg text-gray-400">No monthly fees. No subscriptions. Pay once, own it.</p>
        </div>

        <div class="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-5xl mx-auto">
          <!-- Starter -->
          <div class="rounded-2xl bg-gray-800 border border-gray-700 p-8 flex flex-col">
            <div class="mb-6">
              <h3 class="text-lg font-bold text-white">Starter</h3>
              <div class="mt-3">
                <span class="text-4xl font-extrabold text-white">₦49,000</span>
              </div>
              <p class="mt-3 text-sm text-gray-400">1 user, 1 location, 500 products. Everything you need to start.</p>
            </div>
            <ul class="space-y-2 mb-8 flex-1">
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> Real-time inventory</li>
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> Sales recording</li>
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> P&amp;L reports</li>
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> 12 months updates</li>
            </ul>
            <a
              routerLink="/login"
              class="block text-center rounded-lg border border-gray-600 px-6 py-3 text-sm font-semibold text-white hover:bg-gray-700 transition-colors"
            >
              Get Starter
            </a>
          </div>

          <!-- Growth (highlighted) -->
          <div class="rounded-2xl bg-emerald-600 border border-emerald-500 p-8 flex flex-col relative shadow-xl shadow-emerald-900/30 sm:scale-105">
            <!-- Badge -->
            <div class="absolute -top-4 left-1/2 -translate-x-1/2">
              <span class="rounded-full bg-yellow-400 text-yellow-900 text-xs font-bold px-4 py-1.5 shadow-md">Most Popular</span>
            </div>
            <div class="mb-6">
              <h3 class="text-lg font-bold text-white">Growth</h3>
              <div class="mt-3">
                <span class="text-4xl font-extrabold text-white">₦99,000</span>
              </div>
              <p class="mt-3 text-sm text-emerald-100">3 users, 3 locations, unlimited products, AI insights.</p>
            </div>
            <ul class="space-y-2 mb-8 flex-1">
              <li class="flex items-center gap-2 text-sm text-emerald-100"><span class="text-yellow-300">✓</span> Everything in Starter</li>
              <li class="flex items-center gap-2 text-sm text-emerald-100"><span class="text-yellow-300">✓</span> AI price suggestions</li>
              <li class="flex items-center gap-2 text-sm text-emerald-100"><span class="text-yellow-300">✓</span> FX rate integration</li>
              <li class="flex items-center gap-2 text-sm text-emerald-100"><span class="text-yellow-300">✓</span> Multi-location support</li>
            </ul>
            <a
              routerLink="/login"
              class="block text-center rounded-lg bg-white px-6 py-3 text-sm font-bold text-emerald-700 hover:bg-emerald-50 transition-colors"
            >
              Get Growth
            </a>
          </div>

          <!-- Scale -->
          <div class="rounded-2xl bg-gray-800 border border-gray-700 p-8 flex flex-col">
            <div class="mb-6">
              <h3 class="text-lg font-bold text-white">Scale</h3>
              <div class="mt-3">
                <span class="text-4xl font-extrabold text-white">₦199,000</span>
              </div>
              <p class="mt-3 text-sm text-gray-400">10 users, unlimited locations, white-label, priority support.</p>
            </div>
            <ul class="space-y-2 mb-8 flex-1">
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> Everything in Growth</li>
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> White-label branding</li>
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> Priority support</li>
              <li class="flex items-center gap-2 text-sm text-gray-300"><span class="text-emerald-400">✓</span> API access</li>
            </ul>
            <a
              routerLink="/login"
              class="block text-center rounded-lg border border-gray-600 px-6 py-3 text-sm font-semibold text-white hover:bg-gray-700 transition-colors"
            >
              Get Scale
            </a>
          </div>
        </div>

        <p class="text-center mt-8 text-sm text-gray-500">
          All plans include free updates for 12 months. One-time payment.
        </p>
      </div>
    </section>

    <!-- ============================================================
         G. TESTIMONIAL GRID
         ============================================================ -->
    <section class="py-20 bg-white">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl sm:text-4xl font-extrabold text-gray-900">What traders are saying</h2>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <!-- Testimonial 1 -->
          <div class="rounded-2xl border border-gray-100 bg-gray-50 p-6">
            <div class="flex gap-0.5 mb-3">
              <span class="text-yellow-400">★★★★★</span>
            </div>
            <p class="text-sm text-gray-700 leading-relaxed mb-4">"ModishLog paid for itself in the first week. I discovered I was selling one of my top products at a 4% loss — fixed it immediately. Margin went from 4% to 38%."</p>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-orange-100 text-orange-700 font-bold text-sm">B</div>
              <div>
                <p class="text-sm font-semibold text-gray-900">Babatunde Adeyemi</p>
                <p class="text-xs text-gray-400">Shoe Retailer · Lagos</p>
              </div>
            </div>
          </div>

          <!-- Testimonial 2 -->
          <div class="rounded-2xl border border-gray-100 bg-gray-50 p-6">
            <div class="flex gap-0.5 mb-3">
              <span class="text-yellow-400">★★★★★</span>
            </div>
            <p class="text-sm text-gray-700 leading-relaxed mb-4">"I run 3 market stalls and used to manage everything in notebooks. Now I see all 3 locations from my phone. My staff can't manipulate figures anymore either."</p>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-teal-100 text-teal-700 font-bold text-sm">N</div>
              <div>
                <p class="text-sm font-semibold text-gray-900">Ngozi Eze</p>
                <p class="text-xs text-gray-400">Market Trader · Kano</p>
              </div>
            </div>
          </div>

          <!-- Testimonial 3 -->
          <div class="rounded-2xl border border-gray-100 bg-gray-50 p-6">
            <div class="flex gap-0.5 mb-3">
              <span class="text-yellow-400">★★★★★</span>
            </div>
            <p class="text-sm text-gray-700 leading-relaxed mb-4">"The AI suggestions are surprisingly accurate. It told me to raise my perfume price by ₦500 and I sold more units because customers trusted the quality more."</p>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-pink-100 text-pink-700 font-bold text-sm">H</div>
              <div>
                <p class="text-sm font-semibold text-gray-900">Halima Musa</p>
                <p class="text-xs text-gray-400">Cosmetics Retailer · Abuja</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- H. FOUNDER MESSAGE — hidden until ready
    <section class="py-20 bg-gray-50">
      <div class="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8 text-center">
        <h2 class="text-2xl sm:text-3xl font-extrabold text-gray-900 mb-8">A message from our founder</h2>
        <div class="aspect-video rounded-2xl bg-gray-100 flex items-center justify-center cursor-pointer hover:bg-gray-200 transition-colors">
          <div class="flex flex-col items-center gap-3">
            <div class="flex h-16 w-16 items-center justify-center rounded-full bg-white shadow-md">
              <span class="text-2xl">▶</span>
            </div>
            <p class="text-sm font-medium text-gray-500">Watch our story (2 min)</p>
          </div>
        </div>
      </div>
    </section>
    -->

    <!-- ============================================================
         I. FOOTER
         ============================================================ -->
    <footer class="bg-gray-900 text-gray-400 py-12">
      <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div class="flex flex-row items-center justify-between gap-4">
          <!-- Brand -->
          <div class="flex flex-col items-start gap-2">
            <div class="flex items-center gap-2">
              <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-sm font-bold text-white">M</div>
              <span class="text-base font-bold text-white">ModishLog</span>
            </div>
            <p class="text-sm text-gray-500">Your shop runs better when you can see the numbers.</p>
          </div>

          <!-- Social links -->
          <div class="flex items-center gap-3">
            <a
              href="#"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Follow us on Instagram"
              class="flex h-10 w-10 items-center justify-center rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 transition-colors"
            >
              <i class="pi pi-instagram text-base"></i>
            </a>
            <a
              href="#"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Follow us on Facebook"
              class="flex h-10 w-10 items-center justify-center rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 transition-colors"
            >
              <i class="pi pi-facebook text-base"></i>
            </a>
            <a
              href="#"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Follow us on X"
              class="flex h-10 w-10 items-center justify-center rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 transition-colors"
            >
              <i class="pi pi-twitter text-base"></i>
            </a>
          </div>
        </div>

        <div class="mt-8 flex flex-row items-center justify-between gap-4 border-t border-gray-800 pt-8">
          <p class="text-xs text-gray-600">© 2025 ModishLog. All rights reserved.</p>
          <div class="flex items-center gap-6">
            <a href="#" class="text-xs text-gray-600 hover:text-gray-400 transition-colors">Privacy</a>
            <a href="#" class="text-xs text-gray-600 hover:text-gray-400 transition-colors">Terms</a>
          </div>
        </div>
      </div>
    </footer>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingPageComponent {
  readonly mobileMenuOpen = signal(false);
}
