<script setup lang="ts">
const { t } = useI18n()
useSeoMeta({ title: () => t('wishlist.title') })
</script>

<template>
  <div>
    <h2 class="font-serif text-2xl">{{ t('account.nav.wishlist') }}</h2>
    <WishlistGrid grid-class="mt-6 md:grid-cols-3" empty-class="py-16" />
  </div>
</template>
