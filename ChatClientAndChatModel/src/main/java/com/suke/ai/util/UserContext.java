package com.suke.ai.util;

/**
 * @author 自然醒
 * @version 1.0
 * @date 2026-02-09 21:29
 * @description 用于绑定当前用户对话的上下文消息
 */
public class UserContext {
    private static final ThreadLocal<String> currentUserId  = new ThreadLocal<>();

    public static void setCurrentUserId(String userId) {
        currentUserId.set(userId);
    }

    public static String getCurrentUserId() {
        return currentUserId.get();
    }

    public static void clear() {
        currentUserId.remove();
    }
}
