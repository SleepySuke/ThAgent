package com.suke.server.config;

import com.suke.server.tool.TimeTools;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * @author 自然醒
 * @version 1.0
 */
@Configuration
public class MCPServerConfig {

    @Bean
    public ToolCallbackProvider toolCallbackProvider(TimeTools timeTools) {
        return MethodToolCallbackProvider.builder().toolObjects(timeTools).build();
    }
}
