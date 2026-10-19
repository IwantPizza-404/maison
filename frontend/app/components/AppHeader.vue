<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useSiteStore } from '~/stores/site'
import { useWishlistStore } from '~/stores/wishlist'

const { t } = useI18n()
const localePath = useLocalePath()
const cart = useCartStore()
const site = useSiteStore()
const auth = useAuthStore()
const wishlist = useWishlistStore()

const watches = (query: Record<string, string> = {}) => localePath({ path: '/watches', query })

// Колонки мега-меню «Часы»
const menuColumns = computed(() => [
  {
    title: t('menu.forWhom'),
    links: [
      { label: t('menu.men'), to: watches({ gender: 'men' }) },
      { label: t('menu.women'), to: watches({ gender: 'women' }) },
      { label: t('menu.unisex'), to: watches({ gender: 'unisex' }) },
    ],
  },
  {
    title: t('menu.collections'),
    links: [
      { label: t('menu.all'), to: watches() },
      { label: t('menu.new'), to: watches({ condition: 'new' }) },
      { label: t('nav.preowned'), to: watches({ condition: 'pre_owned' }) },
      { label: t('menu.inStock'), to: watches({ availability: 'in_stock' }) },
      { label: t('menu.onOrder'), to: watches({ availability: 'on_order' }) },
    ],
  },
])

const topBrands = computed(() => site.brands.slice(0, 12))

// Активный пункт считаем сами: по умолчанию ссылка активна по пути без учёта параметров,
// и «Pre-owned» (/watches?condition=pre_owned) подсвечивалась бы на всём каталоге
const route = useRoute()
const routeBaseName = useRouteBaseName()
const section = computed(() => {
  const name = String(routeBaseName(route) ?? '')
  const condition = ([] as unknown[]).concat(route.query.condition ?? [])
  if (name === 'watches' && condition.includes('pre_owned')) return 'preowned'
  if (name.startsWith('watches')) return 'watches'
  if (name.startsWith('brands')) return 'brands'
  return null
})

// exactQuery отключает встроенную проверку Nuxt UI (она сравнивает только путь);
// цвет задаём классом — у пункта с выпадающим меню нет атрибута data-active
const navItem = (key: string, item: NavigationMenuItem): NavigationMenuItem => ({
  ...item,
  exactQuery: true,
  active: section.value === key,
  class: section.value === key ? 'text-gold-500' : undefined,
})

const links = computed<NavigationMenuItem[]>(() => [
  navItem('watches', { label: t('nav.watches'), to: watches(), slot: 'watches' as const }),
  navItem('brands', { label: t('nav.brands'), to: localePath('/brands') }),
  navItem('preowned', { label: t('nav.preowned'), to: watches({ condition: 'pre_owned' }) }),
])

// Мобильное меню — простой вертикальный список
const mobileLinks = computed<NavigationMenuItem[]>(() => [
  {
    label: t('nav.watches'),
    active: section.value === 'watches',
    children: menuColumns.value.flatMap((c) => c.links).map((link) => ({ ...link, exactQuery: true })),
  },
  {
    label: t('nav.brands'),
    active: section.value === 'brands',
    children: [
      { label: t('brands.all'), to: localePath('/brands'), exact: true },
      ...site.brands.map((b) => ({ label: b.name, to: localePath(`/brands/${b.slug}`) })),
    ],
  },
  { label: t('nav.preowned'), to: watches({ condition: 'pre_owned' }), active: section.value === 'preowned' },
])

const announcementLink = useSiteLink()
</script>

<template>
  <div>
    <!-- Строка объявления (настраивается в админке) -->
    <div v-if="site.settings?.announcement" class="bg-gold-500 px-4 py-2 text-center text-xs uppercase tracking-[0.18em] text-ink">
      <NuxtLink v-if="site.settings.announcement_link" :to="announcementLink(site.settings.announcement_link)" class="hover:underline">
        {{ site.settings.announcement }}
      </NuxtLink>
      <span v-else>{{ site.settings.announcement }}</span>
    </div>

    <UHeader
      :to="localePath('/')"
      :ui="{
        root: 'bg-ink border-none text-white',
        toggle: 'text-white',
        content: 'bg-ink',
      }"
    >
      <template #title>
        <span class="font-serif text-2xl tracking-[0.3em] text-gold-500">MAISON</span>
      </template>

      <!--
        Мега-меню: тёмная панель в цвет шапки. Ширина задана явно — иначе Nuxt UI меряет панель
        по содержимому, а оно тянется по панели, и колонки обрезаются. shrink-0 — панель лежит
        во flex-контейнере шириной с меню и без этого сжималась бы до него.
      -->
      <UNavigationMenu
        :items="links"
        variant="link"
        :ui="{
          link: 'text-xs uppercase tracking-[0.2em] text-white/80 hover:text-gold-500 data-[state=open]:text-gold-500',
          linkTrailingIcon: 'text-current',
          viewportWrapper: 'justify-center',
          viewport: 'shrink-0 sm:w-[min(56rem,92vw)] sm:left-0 rounded-none bg-ink ring-0 border-t border-gold-500/40 shadow-2xl shadow-black/50',
          content: 'w-full',
        }"
      >
        <template #watches-content>
          <div class="grid grid-cols-[2fr_1fr_1fr] gap-10 p-10 text-white">
            <div>
              <p class="mb-5 text-xs font-medium uppercase tracking-[0.2em] text-white/50">{{ t('nav.brands') }}</p>
              <ul class="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                <li v-for="brand in topBrands" :key="brand.slug">
                  <NuxtLink :to="localePath(`/brands/${brand.slug}`)" class="text-white/80 transition-colors hover:text-gold-500">
                    {{ brand.name }}
                  </NuxtLink>
                </li>
              </ul>
              <NuxtLink
                :to="localePath('/brands')"
                class="mt-6 inline-block border-b border-gold-500 pb-0.5 text-xs uppercase tracking-[0.2em] text-gold-500 hover:text-gold-300"
              >
                {{ t('brands.all') }}
              </NuxtLink>
            </div>
            <div v-for="column in menuColumns" :key="column.title">
              <p class="mb-5 text-xs font-medium uppercase tracking-[0.2em] text-white/50">{{ column.title }}</p>
              <ul class="space-y-3 text-sm">
                <li v-for="item in column.links" :key="item.label">
                  <NuxtLink :to="item.to" class="text-white/80 transition-colors hover:text-gold-500">{{ item.label }}</NuxtLink>
                </li>
              </ul>
            </div>
          </div>
        </template>
      </UNavigationMenu>

      <template #right>
        <SearchModal />
        <CurrencySwitcher />
        <LanguageSwitcher />
        <UChip :text="wishlist.count" :show="wishlist.count > 0" size="3xl" color="primary" inset class="hidden sm:inline-flex">
          <UButton
            :to="localePath(auth.isLoggedIn ? '/account/wishlist' : '/wishlist')"
            icon="i-lucide-heart"
            :aria-label="t('wishlist.title')"
            variant="ghost"
            class="text-white hover:bg-white/10"
          />
        </UChip>
        <UButton
          :to="localePath(auth.isLoggedIn ? '/account' : '/login')"
          icon="i-lucide-user"
          :aria-label="auth.isLoggedIn ? t('account.title') : t('login.title')"
          variant="ghost"
          class="text-white hover:bg-white/10"
        />
        <UChip :text="cart.count" :show="cart.count > 0" size="3xl" color="primary" inset>
          <UButton
            :to="localePath('/cart')"
            icon="i-lucide-shopping-bag"
            :aria-label="t('cart.title')"
            variant="ghost"
            class="text-white hover:bg-white/10"
          />
        </UChip>
      </template>

      <template #body>
        <!-- Мобильное меню на тёмном фоне: без светлых плашек у активных пунктов -->
        <UNavigationMenu
          :items="mobileLinks"
          orientation="vertical"
          variant="link"
          class="-mx-2.5"
          :ui="{
            link: 'py-3 text-base text-white/80 before:bg-transparent hover:text-gold-500 hover:before:bg-white/5 data-active:text-gold-500 data-active:before:bg-transparent',
            linkTrailingIcon: 'text-white/50',
            childList: 'border-white/10',
            childLink: 'text-white/70 hover:text-gold-500 data-active:text-gold-500',
          }"
        />
      </template>
    </UHeader>
  </div>
</template>
