// Единое место со всеми ключами кеша react-query.
// Если нужно обновить сразу много данных, используют общий «корень»:
// например invalidateQueries({ queryKey: qk.products }) обновит и каталог, и карточки.
export const qk = {
  // Пользователь
  me: ["me"] as const,
  sessions: ["sessions"] as const,

  // Категории
  categories: ["categories"] as const,
  category: (slug: string) => ["categories", slug] as const,

  // Товары (корень "products" объединяет всё ниже)
  products: ["products"] as const,
  recommendations: (params: object) =>
    ["products", "recommendations", params] as const,
  catalog: (filters: object) => ["products", "catalog", filters] as const,
  catalogInfinite: (filters: object) =>
    ["products", "catalog-infinite", filters] as const,
  product: (slug: string) => ["products", "detail", slug] as const,

  // Избранное
  likes: ["likes"] as const,
  myLikes: (params: object) => ["likes", "mine", params] as const,

  // Отзывы
  reviews: ["reviews"] as const,
  productReviews: (productId: number, params: object) =>
    ["reviews", "product", productId, params] as const,
  reviewSummary: (productId: number) =>
    ["reviews", "summary", productId] as const,
  myReviews: (params: object) => ["reviews", "mine", params] as const,
  pendingReviews: (params: object) => ["reviews", "pending", params] as const,
  userReviews: (userId: number, params: object) =>
    ["reviews", "user", userId, params] as const,

  // Заказы
  orders: ["orders"] as const,
  myOrders: (params: object) => ["orders", "mine", params] as const,
  order: (orderId: number) => ["orders", "detail", orderId] as const,
  adminOrders: (params: object) => ["orders", "admin", params] as const,
  userOrders: (userId: number, params: object) =>
    ["orders", "user", userId, params] as const,

  // Админка: парсер и система
  parserStatus: ["parser", "status"] as const,
  parserQueueStats: ["parser", "queue-stats"] as const,
  parserQueue: (params: object) => ["parser", "queue", params] as const,
  health: ["health"] as const,
};
